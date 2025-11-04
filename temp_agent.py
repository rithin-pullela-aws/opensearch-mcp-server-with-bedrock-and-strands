# app.py
import os
import json
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

system_prompt = """
helpful agent
"""


# Bedrock model: enable streaming to get partial tokens back
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name=os.getenv("AWS_REGION", "us-east-1"),
    streaming=False,
)

# --- MCP via Streamable HTTP ---
# Point this at your MCP server’s Streamable HTTP endpoint (tool hub, searcher, etc.)
MCP_URL = os.getenv("MCP_URL", "http://localhost:9200/_plugins/_ml/mcp/")
MCP_HEADERS = {}
if "MCP_BEARER" in os.environ:
    MCP_HEADERS["Authorization"] = f"Bearer {os.getenv('MCP_BEARER')}"

mcp_client = MCPClient(lambda: streamablehttp_client(MCP_URL, headers=MCP_HEADERS))

# Build the Strands agent with model, system prompt, and MCP tools (managed integration)
agent = Agent(
    model=model,
    system_prompt=system_prompt
)

# --- AgentCore Runtime wrapper ---
app = BedrockAgentCoreApp()

# default_match_all_query = '{"query":{"match_all":{}}}'
# def extract_json(response) -> dict:
#     """
#     Extract the JSON object from the response, even if it's embedded within other text.
#     Handles cases like: "something blah blah {\"key\": \"value\"} blah blah"
#     Similar to Java's ObjectMapper.readTree() approach.
#     """
#     # If response is already a dict, return it directly
#     if isinstance(response, dict):
#         return response
    
#     # Handle string responses
#     if not response or not isinstance(response, str) or not response.strip():
#         raise ValueError("Invalid JSON: response is empty or invalid type")
    
#     # First, try to parse the entire response as JSON
#     try:
#         return json.loads(response)
#     except json.JSONDecodeError:
#         pass
    
#     # Find first '{' - look for JSON object only
#     start_idx = response.find('{')
#     if start_idx == -1:
#         raise ValueError("No JSON object found in response: missing opening brace")
    
#     # Use JSONDecoder.raw_decode() which parses from a position and finds the end automatically
#     # This is similar to Jackson's readTree() behavior
#     decoder = json.JSONDecoder()
#     try:
#         obj, end_idx = decoder.raw_decode(response, start_idx)
        
#         # Verify it's a dict (JSON object), not a list or primitive
#         if not isinstance(obj, dict):
#             raise ValueError("Extracted JSON is not an object")
        
#         return obj
#     except json.JSONDecodeError as e:
#         raise ValueError(f"Failed to extract JSON object from text: {e}")

    
# Simple JSON in, JSON/stream out contract for AgentCore /invocations
@app.entrypoint
async def invoke(payload):
    """
    Expected payload: {"prompt": "...", "metadata": {...}} 
    """
    print(f"Received payload: {payload}")
    user_prompt = payload.get("prompt", "")
    print(f"User prompt: {user_prompt}")
    # Clear previous conversation history to start fresh
    # agent.messages.clear()
    # Stream tokens/events back to the client
    result = agent(user_prompt)
    print("result is mawaaaaa: ", result)

    resss= result.message
    print("resss is mawaaaaa: ", resss)
    print("type of resss: ", type(resss))
    return resss
    
if __name__ == "__main__":
    print("Starting agent example...")
    app.run()