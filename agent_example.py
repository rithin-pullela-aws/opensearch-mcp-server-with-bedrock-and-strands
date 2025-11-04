"""
OpenSearch Agentic Search with AWS Bedrock and MCP

This agent translates natural language queries into OpenSearch DSL queries
using AWS Bedrock (Claude Sonnet) and the Model Context Protocol (MCP).

Configuration is managed through environment variables (.env file).
See README.md for setup instructions.
"""
import os
import json
import base64
import ssl
import warnings
from pathlib import Path
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, will use system environment variables

# SSL verification configuration - must be set before any SSL connections
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() in ("true", "1", "yes")
if not VERIFY_SSL:
    # Disable SSL warnings when verification is disabled
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Monkey-patch SSL module to create unverified contexts globally
    _original_create_default_context = ssl.create_default_context
    
    def _create_unverified_context(purpose=ssl.Purpose.SERVER_AUTH, *args, **kwargs):
        ctx = _original_create_default_context(purpose, *args, **kwargs)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    
    ssl.create_default_context = _create_unverified_context
    
    print("⚠️  SSL verification disabled - use only in development!")

# =============================================================================
# AGENT SYSTEM PROMPT
# =============================================================================

DEFAULT_SYSTEM_PROMPT = """
==== PURPOSE ====
 Produce correct OpenSearch DSL by orchestrating tools. You MUST call the Query Planner Tool (query_planner_tool, "qpt") to author the DSL. 
 Your job: (a) gather only essential factual context, (b) compose a self-contained natural-language question for qpt, (c) validate coverage of qpt's DSL and iterate if needed, then (d) return a strict JSON result with the DSL and a brief step trace.

 ==== OUTPUT CONTRACT (STRICT) ====
 Return ONLY a valid JSON object with exactly one key:
 {"dsl_query": <OpenSearch DSL Object>}
 - No markdown, no extra text, no code fences. Double-quote all keys/strings.
 - Escape quotes that appear inside values.
 - The output MUST parse as JSON.

 ==== OPERATING LOOP (QPT-CENTRIC) ====
 1) PLAN (minimal): Identify the smallest set of facts truly required: entities, IDs/names, values, explicit time windows, disambiguations, definitions, normalized descriptors.
 2) COLLECT (as needed): Use tools to fetch ONLY those facts. (explain before using tool)
 3) Before calling each tool, briefly explain the context you have and what you are about in this tool call to do and why.
 4) SELECT index_name:
 - If provided by the caller, use it as-is.
 - Otherwise, discover and choose a single best index (e.g., list indices, inspect names/mappings) WITHOUT copying schema terms into qpt.question.
 5) COMPOSE qpt.question: One concise, clear, self-contained natural-language question containing:
 - Do NOT mention schema fields, analyzers, or DSL constructs to the qpt.
 - The user's request (no schema/DSL hints), and
 - The factual context you resolved (verbatim values, IDs, names, explicit date ranges, normalized descriptors).
 This question is the ONLY context (besides index_name) that qpt relies on.
 6) CALL qpt with {question, index_name, embedding_model_id(if available)}.
 7) VALIDATE qpt response and ensure it answers user's question else iterate by providing more context
 8) FINALIZE when qpt produces a plausible, fully covered DSL.

 ==== CONTEXT RULES ====
 - Use tools to resolve needed facts.
 - When tools return user-specific values, RESTATE them verbatim in qpt.question in pure natural language.
 - NEVER mention schema/field names, analyzers, or DSL constructs in qpt.question.
 - Resolve ambiguous references BEFORE the final qpt call.

  ==== FAILURE MODE ====
 If required context is unavailable or qpt cannot produce a valid DSL
 - Set "dsl_query" to {"query":{"match_all":{}}}

  ==== STYLE & SAFETY ====
 - qpt.question must be purely natural-language and context-only.
 - Be minimal and deterministic; avoid speculation.
 - Always produce valid JSON per the contract.
 - Before calling each tool, briefly explain the context you have and what you are about in this tool call to do and why.

==== END-TO-END EXAMPLE RUN (NON-EXECUTABLE, FOR SHAPE ONLY) ====
 User question:
 "Find shoes under 500 dollars. I am so excited for shoes yay!"

 Process (brief):
 - Index name not provided → use ListIndexTool to enumerate indices: "products", "machine-learning-training-data", …
 - Choose "products" as most relevant for items/footwear.
 - Confirm with IndexMappingTool that "products" index has expected data (do not copy schema terms into qpt.question).
 - Compose qpt.question with natural-language constraints only.
 - Call qpt and validate.
 - In every tool call briefly explain the context you have and what you are about in this tool call to do and why.

 qpt.question (self-contained, no schema terms):
 "Find Shoes under 500 dollars."

 qpt.output:
 "{\"query\":{\"bool\":{\"must\":[{\"match\":{\"category\":\"Shoes\"}}],\"filter\":[{\"range\":{\"price\":{\"lte\":500}}}]}}}"

 Final response JSON:
 {
 "dsl_query":{"query":{"bool":{"must":[{"match":{"category":"Shoes"}}],"filter":[{"range":{"price":{"lte":500}}}]}}}
 }
"""

def load_system_prompt():
    """Load system prompt from environment, file, or use default."""
    # First, check if SYSTEM_PROMPT is set directly
    if os.getenv("SYSTEM_PROMPT"):
        return os.getenv("SYSTEM_PROMPT")
    
    # Second, check if SYSTEM_PROMPT_FILE is set
    prompt_file = os.getenv("SYSTEM_PROMPT_FILE")
    if prompt_file and Path(prompt_file).exists():
        with open(prompt_file, 'r') as f:
            return f.read()
    
    # Default to the built-in prompt
    return DEFAULT_SYSTEM_PROMPT

system_prompt = load_system_prompt()

# =============================================================================
# BEDROCK MODEL CONFIGURATION
# =============================================================================

model = BedrockModel(
    model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
    region_name=os.getenv("AWS_REGION", "us-east-1"),
    streaming=False,
)

# =============================================================================
# MCP CLIENT CONFIGURATION
# =============================================================================

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")

# MCP endpoint configuration
MCP_URL = os.getenv("MCP_URL", f"{OPENSEARCH_URL}/_plugins/_ml/mcp/")

# Setup authentication headers
MCP_HEADERS = {}
if "MCP_BEARER" in os.environ:
    MCP_HEADERS["Authorization"] = f"Bearer {os.getenv('MCP_BEARER')}"
elif OPENSEARCH_USERNAME and OPENSEARCH_PASSWORD:
    credentials = base64.b64encode(f"{OPENSEARCH_USERNAME}:{OPENSEARCH_PASSWORD}".encode()).decode()
    MCP_HEADERS["Authorization"] = f"Basic {credentials}"

# Create MCP client with custom transport factory for SSL verification control
def create_mcp_transport():
    """
    Custom transport factory that creates an MCP transport with SSL verification control.
    The SSL context is configured globally via monkey-patching when VERIFY_SSL=false.
    """
    return streamablehttp_client(MCP_URL, headers=MCP_HEADERS)

mcp_client = MCPClient(transport_callable=create_mcp_transport)

# =============================================================================
# AGENT INITIALIZATION
# =============================================================================

agent = Agent(
    model=model,
    system_prompt=system_prompt,
    tools=[mcp_client],
)

# =============================================================================
# AGENTCORE RUNTIME & HELPER FUNCTIONS
# =============================================================================

app = BedrockAgentCoreApp()

DEFAULT_MATCH_ALL_QUERY = '{"query":{"match_all":{}}}'

def extract_json(response) -> dict:
    """
    Extract the JSON object from the response, even if it's embedded within other text.
    Handles cases like: "something blah blah {\"key\": \"value\"} blah blah"
    Similar to Java's ObjectMapper.readTree() approach.
    """
    # If response is already a dict, return it directly
    if isinstance(response, dict):
        return response
    
    # Handle string responses
    if not response or not isinstance(response, str) or not response.strip():
        raise ValueError("Invalid JSON: response is empty or invalid type")
    
    # First, try to parse the entire response as JSON
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # Find first '{' - look for JSON object only
    start_idx = response.find('{')
    if start_idx == -1:
        raise ValueError("No JSON object found in response: missing opening brace")
    
    # Use JSONDecoder.raw_decode() which parses from a position and finds the end automatically
    # This is similar to Jackson's readTree() behavior
    decoder = json.JSONDecoder()
    try:
        obj, end_idx = decoder.raw_decode(response, start_idx)
        
        # Verify it's a dict (JSON object), not a list or primitive
        if not isinstance(obj, dict):
            raise ValueError("Extracted JSON is not an object")
        
        return obj
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to extract JSON object from text: {e}")

# =============================================================================
# ENTRYPOINT
# =============================================================================

@app.entrypoint
async def invoke(payload: dict):
    """
    Expected payload: {"prompt": "...", "metadata": {...}} 
    """
    print(f"Received payload: {payload}")
    user_prompt = payload.get("prompt", "")
    print(f"User prompt: {user_prompt}")
    # Clear previous conversation history to start fresh
    agent.messages.clear()
    # Stream tokens/events back to the client
    result = agent(user_prompt)
    print(f"result.message (original): {result.message}")

    # Extract the text from result.message['content'][0]['text']
    # result.message is always a dict: {'role': 'assistant', 'content': [{'text': '...'}]}
    message_text = result.message['content'][0]['text']
    print(f"Original text (with possible wrapper text): {message_text}")

    # Extract just the JSON part from the text (removes any surrounding text)
    # The extract_json function finds the first '{' and parses the complete JSON object
    try:
        parsed_json = extract_json(message_text)
        print(f"Parsed JSON (text removed): {parsed_json}")
        cleaned_json = parsed_json.get("dsl_query", json.loads(DEFAULT_MATCH_ALL_QUERY))
        cleaned_json_string = json.dumps(cleaned_json)
        print(f"Cleaned JSON string: {cleaned_json_string}")
        
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Failed to extract JSON from response: {e}")
        cleaned_json_string = DEFAULT_MATCH_ALL_QUERY

    # Replace the text content with the cleaned JSON string
    result.message['content'][0]['text'] = cleaned_json_string
    print(f"result.message (cleaned): {result.message}")

    return result.message

if __name__ == "__main__":
    print("Starting Bedrock Agent with OpenSearch MCP integration...")
    print(f"Connecting to: {OPENSEARCH_URL}")
    app.run()