# MCP Network Bridge for Mixed Content Types

This Python-based MCP bridge connects to remote/network MCP servers (like the HuskyLens2 camera) and properly handles mixed content types that the standard CLI bridge doesn't support.

## Problem Solved

1. **Network MCP Servers**: Connects to MCP servers running on network devices (like the HuskyLens2 camera) rather than local processes
2. **Mixed Content Types**: The standard MCP CLI bridge fails when servers return `resource_link` alongside text. This bridge extracts the text content while preserving resource metadata

## Features

- Connects to remote MCP servers via HTTP/SSE
- Handles mixed content types (text, resource_link, etc.)
- Provides clean HTTP REST API for tool calls
- CORS support for web applications
- Debug logging support
- Automatic initialization and connection management

## Installation

```bash
pip install aiohttp aiohttp-sse
```

## Usage

### For Network MCP Servers (like HuskyLens2)

If your HuskyLens2 camera is at `192.168.1.100:8080`:

```bash
# Connect to HuskyLens2 camera on network
python network_mcp_bridge.py --mcp-server http://192.168.1.100:8080

# Or if you have a hostname
python network_mcp_bridge.py --mcp-server http://huskylens.local:8080

# With custom bridge port (if 8080 is taken)
python network_mcp_bridge.py --mcp-server http://192.168.1.100:8080 --port 8081

# With debug logging to see what's happening
python network_mcp_bridge.py --mcp-server http://192.168.1.100:8080 --debug

# Make bridge accessible from other machines
python network_mcp_bridge.py --mcp-server http://192.168.1.100:8080 --host 0.0.0.0
```

### API Endpoints

The bridge exposes these endpoints:

- `GET /` - Info page with available endpoints
- `GET /health` - Health check and connection status
- `GET /tools` - List available tools from the MCP server
- `POST /call` - Call a tool on the MCP server

### Example Tool Calls

```bash
# Get what the HuskyLens sees
curl -X POST http://localhost:8080/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "Huskylens2:get_recognition_result",
    "arguments": {
      "operation": "get_result"
    }
  }'

# Check current algorithm
curl -X POST http://localhost:8080/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "Huskylens2:manage_applications",
    "arguments": {
      "operation": "current_application"
    }
  }'

# List available algorithms
curl -X POST http://localhost:8080/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "Huskylens2:manage_applications",
    "arguments": {
      "operation": "application_list"
    }
  }'
```

### Python Client Example

```python
import requests

# Connect through the bridge
bridge_url = "http://localhost:8080"

# Check what the camera sees
response = requests.post(
    f"{bridge_url}/call",
    json={
        "tool": "Huskylens2:get_recognition_result",
        "arguments": {"operation": "get_result"}
    }
)

result = response.json()
print(result["result"]["content"])  # Will show detection results
```

## How It Works

1. **Connection**: The bridge connects to your HuskyLens2 (or other MCP server) over HTTP
2. **Mixed Content Handling**: When the camera returns both image links and detection data:
   - Extracts text content (detection JSON)
   - Preserves image metadata as text annotations
   - Returns a unified text response
3. **Clean API**: Exposes a simple REST API that any tool can consume

## Response Processing Example

When HuskyLens2 returns:
```json
{
  "content": [
    {
      "type": "resource_link",
      "mimeType": "image/png",
      "name": "带标注的结果图像",
      "uri": "19700101_004312_1280x720.png"
    },
    {
      "type": "text",
      "text": "[{\"name\": \"bottle\", \"conf\": 0.307, \"x\": 128, \"y\": 71}]"
    }
  ]
}
```

The bridge returns:
```json
{
  "result": {
    "isError": false,
    "content": "[Image: 带标注的结果图像 (image/png) - 19700101_004312_1280x720.png]\n[{\"name\": \"bottle\", \"conf\": 0.307, \"x\": 128, \"y\": 71}]"
  }
}
```

## Use Cases

- Connect Claude or other AI tools to HuskyLens2 camera
- Bridge network-based MCP servers to local tools
- Debug MCP server responses with mixed content
- Create web applications that interact with MCP servers

## Troubleshooting

1. **Connection Failed**: 
   - Check the MCP server URL is correct
   - Ensure the device is on the same network
   - Try using IP address instead of hostname

2. **Port Already in Use**:
   - Use `--port` to specify a different port for the bridge

3. **No Response from Camera**:
   - Enable debug mode with `--debug` to see detailed logs
   - Check if the camera's MCP server is running

4. **Mixed Content Issues**:
   - The bridge automatically handles resource_link types
   - Check debug logs to see the raw response structure