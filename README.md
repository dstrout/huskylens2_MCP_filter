# Huskylens MCP Bridge Server

A transparent proxy server that enables Claude Desktop (and other MCP clients) to work with the Huskylens AI camera's embedded MCP server by filtering out unsupported image data from responses.

## Problem

The Huskylens camera has an embedded Model Context Protocol (MCP) server that returns both image data and text data in its `get_recognition_result` tool responses. However, Claude Desktop's MCP interface cannot handle the image data format returned by the camera, resulting in "The tool returned content in an unsupported format" errors.

The Huskylens MCP server is hardcoded in the camera firmware to always return both image and text data, with no option to request text-only responses.

## Solution

This bridge server sits between Claude Desktop and the Huskylens camera, acting as a transparent filtering proxy. **The bridge works alongside `npx mcp-remote`** - you still use `mcp-remote` to connect Claude Desktop to the bridge, which then connects to the camera.

**Connection chain:**
```
Claude Desktop → mcp-remote → Bridge Server (this program) → Huskylens Camera
```

The bridge:

1. Forwards all MCP protocol messages bidirectionally
2. Filters out `resource_link` items with `mimeType: "image/png"` from tool responses
3. Preserves all text/JSON content so Claude can access the recognition data
4. Maintains proper MCP protocol message ordering

## Features

- **Transparent proxying**: All MCP messages are forwarded without modification except for image filtering
- **Message ordering**: Ensures `notifications/initialized` is sent before other requests (MCP protocol requirement)
- **Multi-session support**: Handles multiple concurrent Claude Desktop sessions
- **SSE streaming**: Properly handles Server-Sent Events (SSE) for real-time communication
- **Configurable**: Command-line arguments for target URL, host, and port
- **Logging**: Clear logging of connections, sessions, and filtered content

## Requirements

- Python 3.7+
- Flask
- requests
- npx (for mcp-remote)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/dstrout/huskylens2_MCP_filter.git
cd huskylens2_MCP_filter
```

2. Install Python dependencies:
```bash
pip3 install flask requests
```

## Usage

### Step 1: Start the Bridge Server

```bash
python3 huskylens_bridge.py --target http://192.168.1.161:3000
```

Replace `192.168.1.161:3000` with your Huskylens camera's IP address and port.

This will:
- Connect to the Huskylens MCP server at the target URL
- Start the bridge server on `http://0.0.0.0:8080`

### Step 2: Configure Claude Desktop

Add the bridge to your Claude Desktop configuration file (`claude_desktop_config.json`):

**Location of config file:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

**Add this entry:**
```json
{
  "mcpServers": {
    "Huskylens2": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://localhost:8080/sse",
        "--allow-http"
      ]
    }
  }
}
```

**Important:** The `mcp-remote` tool connects to the bridge at `localhost:8080`, not directly to the camera. The bridge then proxies to the camera.

### Step 3: Restart Claude Desktop

Restart Claude Desktop and the Huskylens tools should appear in the settings and work without errors.

### Command Line Options

```
--target URL    Required. Target Huskylens MCP server URL
                Example: http://192.168.1.161:3000

--host HOST     Host to bind the bridge server to (default: 0.0.0.0)
                Use 127.0.0.1 to bind to localhost only

--port PORT     Port to bind the bridge server to (default: 8080)

--verbose       Enable verbose debug logging

--no-validation Skip connection validation at startup
```

### Examples

**Custom bridge port:**
```bash
python3 huskylens_bridge.py --target http://192.168.1.161:3000 --port 9000
```

Then update Claude config to use `http://localhost:9000/sse`

**Localhost only:**
```bash
python3 huskylens_bridge.py --target http://192.168.1.161:3000 --host 127.0.0.1
```

**With verbose logging:**
```bash
python3 huskylens_bridge.py --target http://192.168.1.161:3000 --verbose
```

**Skip startup validation (if camera offline):**
```bash
python3 huskylens_bridge.py --target http://192.168.1.161:3000 --no-validation
```

## How It Works

### Architecture

```
┌─────────────────┐    npx mcp-remote    ┌──────────────────┐    HTTP/SSE    ┌─────────────────┐
│ Claude Desktop  │ ◄─────────────────► │  Bridge Server   │ ◄────────────► │ Huskylens Camera│
│  (MCP Client)   │                      │  (This Program)  │                │  (MCP Server)   │
└─────────────────┘                      └──────────────────┘                └─────────────────┘
                                                  │
                                         Filters out images
                                         Preserves text data
```

### Message Flow

1. **Connection**: Claude Desktop uses `mcp-remote` to connect to the bridge via SSE
2. **Session Setup**: Bridge establishes upstream connection to Huskylens camera
3. **Message Ordering**: Bridge buffers tool requests until session is initialized
4. **Filtering**: Image resources are removed from `get_recognition_result` responses
5. **Forwarding**: All other content passes through unchanged

### What Gets Filtered

The bridge only filters `resource_link` items with image MIME types from tool responses:

**Before filtering (from Huskylens):**
```json
{
  "result": {
    "content": [
      {
        "type": "resource_link",
        "uri": "data:image/png;base64,iVBORw0KG...",
        "mimeType": "image/png"
      },
      {
        "type": "text",
        "text": "[{\"id\":1,\"x\":120,\"y\":80,...}]"
      }
    ]
  }
}
```

**After filtering (to Claude):**
```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "[{\"id\":1,\"x\":120,\"y\":80,...}]"
      }
    ]
  }
}
```

## Troubleshooting

### Bridge won't start

**Error**: `Failed to connect to http://192.168.1.161:3000`

**Solution**:
- Verify the Huskylens camera is on and connected to your network
- Check the IP address is correct (may change if using DHCP)
- Ensure the Huskylens MCP server is running (usually on port 3000)
- Use `--no-validation` to skip the startup check

### Tools not appearing in Claude Desktop

**Solution**:
1. Check that the bridge server is running
2. Verify Claude Desktop config points to `http://localhost:8080/sse` (not the camera directly)
3. Restart Claude Desktop completely
4. Check bridge server logs for connection attempts

### Port already in use

**Error**: `Address already in use`

**Solution**:
- Use `--port` to specify a different port
- Or stop the process using port 8080: `lsof -ti:8080 | xargs kill`

### Connection drops or timeouts

**Solution**:
- Ensure stable network connection to Huskylens
- Check for firewall blocking connections
- Enable verbose logging to see what's happening

### Verbose logging for debugging

Run with `--verbose` to see detailed message flow:

```bash
python3 huskylens_bridge.py --target http://192.168.1.161:3000 --verbose
```

## Technical Details

### MCP Protocol Support

- Protocol Version: 2024-11-05 (and later)
- Transport: SSE (Server-Sent Events) over HTTP
- Message ordering: Enforces MCP initialization sequence
- Sessions: Automatic cleanup on disconnect

### Dependencies

- **Flask**: Web framework for HTTP/SSE endpoints
- **requests**: HTTP client for upstream connections
- **mcp-remote**: npm package that bridges Claude Desktop to HTTP MCP servers

### Endpoints

- `GET /sse` - SSE endpoint for MCP client connections (mcp-remote connects here)
- `POST /message?session_id=<id>` - Message forwarding endpoint
- `GET /health` - Health check endpoint

## License

MIT License - See LICENSE file for details

## Contributing

Improvements and bug fixes are welcome! Key areas:

- Better error handling and recovery
- Configuration file support
- Multiple upstream server support
- Performance optimizations

## Acknowledgments

- Huskylens team for creating the AI camera and MCP server
- Anthropic for Claude Desktop and MCP protocol
- The MCP community for `mcp-remote` tool

## Version History

- **1.0.0** (2025-11-12)
  - Initial release
  - Image filtering from tool responses
  - MCP protocol message ordering
  - Command-line configuration
  - Multi-session support
