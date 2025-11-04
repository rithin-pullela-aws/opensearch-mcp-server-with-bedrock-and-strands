# OpenSearch MCP Server with Bedrock and Strands

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This project implements an **Agentic Search** system that translates natural language queries into OpenSearch DSL queries using AWS Bedrock, the Strands agent framework, and the Model Context Protocol (MCP).

**Open Source**: This project is released under the MIT License - feel free to use, modify, and distribute as you wish!

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

Create a `.env` file in the project root (copy from `env.example`):

```bash
cp env.example .env
```

Edit `.env` with your configuration:

```bash
# AWS Configuration
AWS_REGION=us-east-1

# Bedrock Model Configuration
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0

# OpenSearch Configuration
OPENSEARCH_URL=http://localhost:9200
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=admin

# MCP Configuration
MCP_URL=http://localhost:9200/_plugins/_ml/mcp/
# Optional: Uncomment if you need bearer token authentication
# MCP_BEARER=your-bearer-token-here

# Optional: Customize the system prompt
# SYSTEM_PROMPT_FILE=custom_prompt.txt
# or set it directly:
# SYSTEM_PROMPT="Your custom system prompt..."
```

**Important**: The `.env` file is gitignored for security. Never commit credentials to version control!

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

All configuration is managed through environment variables (`.env` file):

### Required Variables:
- `AWS_REGION`: AWS region for Bedrock (default: `us-east-1`)
- `OPENSEARCH_URL`: Your OpenSearch cluster URL (default: `http://localhost:9200`)
- `OPENSEARCH_USERNAME`: OpenSearch username (default: `admin`)
- `OPENSEARCH_PASSWORD`: OpenSearch password (default: `admin`)

### Optional Variables:
- `BEDROCK_MODEL_ID`: Bedrock model to use (default: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`)
- `MCP_URL`: OpenSearch MCP endpoint (default: auto-constructed from OPENSEARCH_URL)
- `MCP_BEARER`: Bearer token for MCP authentication (overrides basic auth)
- `SYSTEM_PROMPT`: Custom system prompt as a string
- `SYSTEM_PROMPT_FILE`: Path to file containing custom system prompt

### Custom System Prompts

You can customize the agent's behavior by providing your own system prompt:

**Option 1: Direct environment variable**
```bash
export SYSTEM_PROMPT="Your custom instructions here..."
```

**Option 2: From a file**
```bash
echo "Your custom instructions here..." > my_prompt.txt
export SYSTEM_PROMPT_FILE=my_prompt.txt
```

If neither is set, the agent uses the default prompt optimized for OpenSearch DSL generation.

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

Contributions are welcome! This is an open-source project and we appreciate:

- Bug reports and fixes
- Feature requests and implementations
- Documentation improvements
- Example use cases and tutorials

Please feel free to:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a Pull Request

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

You are free to use, modify, and distribute this software for any purpose, including commercial applications, with no restrictions.

## Support

If you encounter issues or have questions:
- Open an issue on GitHub
- Check existing issues for solutions
- Review the troubleshooting section above

## Acknowledgments

Built with:
- [AWS Bedrock](https://aws.amazon.com/bedrock/) - Foundation model hosting
- [Strands](https://github.com/anthropics/strands) - Agent orchestration framework
- [OpenSearch](https://opensearch.org/) - Search and analytics engine
- [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) - Tool integration protocol

