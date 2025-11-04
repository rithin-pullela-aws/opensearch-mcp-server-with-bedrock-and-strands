# OpenSearch MCP Server with Bedrock and Strands

This project implements an **Agentic Search** system that translates natural language queries into OpenSearch DSL queries using AWS Bedrock, the Strands agent framework, and the Model Context Protocol (MCP).

## Overview

The agent uses:
- **AWS Bedrock** (Claude Sonnet 4.5) for natural language understanding
- **Strands Framework** for agent orchestration
- **MCP (Model Context Protocol)** to connect to OpenSearch tools
- **BedrockAgentCore** for runtime management

The agent can understand natural language questions like "Find shoes under $500" and automatically generate the appropriate OpenSearch DSL query.

## Prerequisites

- Python 3.8+
- AWS Account with Bedrock access
- OpenSearch cluster with ML Commons plugin enabled
- AWS credentials configured

## Installation

1. **Clone the repository:**
```bash
git clone git@github.com:rithin-pullela-aws/opensearch-mcp-server-with-bedrock-and-strands.git
cd opensearch-mcp-server-with-bedrock-and-strands
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables:**
```bash
export AWS_REGION="us-east-1"  # Your AWS region
export MCP_URL="http://localhost:9200/_plugins/_ml/mcp/"  # Your OpenSearch MCP endpoint
export MCP_BEARER="your-bearer-token"  # Optional: if authentication is required
```

## Setup Agentic Search in OpenSearch

Follow these steps to configure Agentic Search in your OpenSearch cluster:

### Step 1: Create a Connector Tool

Create a Lambda connector that will invoke the Bedrock agent:

```bash
POST /_plugins/_ml/connectors/_create
{
  "name": "Lambda connector of simple calculator",
  "description": "Demo connector of lambda function",
  "version": 1,
  "protocol": "http",
  "parameters": {
    "service_name": "lambda"
  },
  "credential": {
    "access": "rand"
  },
  "actions": [
    {
      "action_type": "execute",
      "method": "POST",
      "url": "http://localhost:8080/invocations",
      "headers": {
        "content-type": "application/json"
      },
      "request_body": "{ \"prompt\": \"NLQ is: ${parameters.question}, index_name is: ${parameters.index_name:-}, and the model ID for neural search is: ${parameters.embedding_model_id:-}.\" }"
    }
  ]
}
```

**Note:** Save the `connector_id` from the response - you'll need it in the next step.

### Step 2: Create a Flow Agent with the Connector Tool

Register a flow agent that uses the connector:

```bash
POST /_plugins/_ml/agents/_register
{
    "name": "Agentic Search",
    "type": "flow",
    "description": "this is a test agent",
    "tools": [
        {
            "type": "ConnectorTool",
            "parameters": {
                "connector_id": "PCEKTJoBwAH_C-u4fNUl",  // Replace with your connector_id from Step 1
                "output_processors": [
                    {
                        "type": "jsonpath_filter",
                        "path": "$.inference_results[0].output[0].dataAsMap.content[0].text"
                    }
                ]
            }
        }
    ]
}
```

**Note:** Save the `agent_id` from the response - you'll need it in the next step.

### Step 3: Register the Search Pipeline

Create a search pipeline that uses the agentic query translator:

```bash
PUT /_search/pipeline/no-cache-pipeline
{
    "request_processors": [
        {
            "agentic_query_translator": {
                "agent_id": "7DKRLZoBpTIbg0854Nod"  // Replace with your agent_id from Step 2
            }
        }
    ],
    "response_processors": [
        {
            "agentic_context": {
                "agent_steps_summary": true,
                "dsl_query": true
            }
        }
    ]
}
```

### Step 4: Perform Agentic Search

Now you can search using natural language queries:

```bash
POST /_search?search_pipeline=no-cache-pipeline
{
    "query": {
        "agentic": {
            "query_text": "Find Macbook cases from Case Star"
        }
    }
}
```

The agent will:
1. Understand the natural language query
2. Discover the appropriate index
3. Analyze the index mapping
4. Generate the optimal OpenSearch DSL query
5. Execute the search and return results

## Running the Agent Locally

To test the agent locally:

```bash
python agent_example.py
```

The agent will start on `http://localhost:8080` and accept invocation requests.

### Test Invocation Format

```json
{
    "prompt": "NLQ is: Find shoes under $500, index_name is: products, and the model ID for neural search is: <embedding-model-id>."
}
```

## Project Structure

```
.
├── agent_example.py      # Main agent implementation with DSL generation logic
├── temp_agent.py         # Simplified agent example
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

## How It Works

1. **Natural Language Input**: User provides a query in natural language
2. **Context Gathering**: Agent uses MCP tools to discover indices and mappings
3. **Query Planning**: Agent calls the Query Planner Tool (QPT) with context
4. **DSL Generation**: Agent generates valid OpenSearch DSL
5. **Validation**: Agent validates the DSL covers the user's intent
6. **Execution**: OpenSearch executes the DSL and returns results

## Key Features

- **Zero-shot DSL generation** from natural language
- **Automatic index discovery** and selection
- **Schema-aware query construction** without exposing schema to the user
- **Iterative refinement** for complex queries
- **JSON output contract** for reliable integration

## Configuration

The main configuration options in `agent_example.py`:

- `model_id`: Bedrock model to use (default: Claude Sonnet 4.5)
- `MCP_URL`: OpenSearch MCP endpoint URL
- `AWS_REGION`: AWS region for Bedrock
- `system_prompt`: Detailed instructions for the agent's behavior

## Troubleshooting

**Agent returns match_all query:**
- The agent couldn't understand the query or required context is missing
- Check that MCP tools are accessible and returning valid data

**Connection errors:**
- Verify `MCP_URL` is correct and accessible
- Check AWS credentials are configured
- Ensure Bedrock model access is enabled in your region

**Invalid DSL generated:**
- Review the system prompt for clarity
- Check that index mappings are correct
- Verify the Query Planner Tool is working properly

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[Specify your license here]

## Contact

[Your contact information]

