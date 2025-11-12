#!/usr/bin/env python3
"""
SSE MCP Bridge for HuskyLens2 camera.
Handles session-based SSE protocol.
"""

import json
import asyncio
import aiohttp
from aiohttp import web
import argparse
import logging
from typing import Optional, Dict, Any
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HuskyLensMCPClient:
    def __init__(self, server_url: str):
        """
        Initialize MCP client for HuskyLens2
        
        Args:
            server_url: Base URL of the MCP server (e.g., http://192.168.1.161:3000)
        """
        self.server_url = server_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_id = 0
        self.session_id = None
        self.message_url = None
        
    async def start(self):
        """Start the MCP client"""
        self.session = aiohttp.ClientSession()
        
        # Establish SSE connection and get session
        await self._establish_session()
        
        logger.info(f"MCP client started, connected to {self.server_url}")
    
    async def _establish_session(self):
        """Establish SSE session and extract session ID"""
        try:
            async with self.session.get(f"{self.server_url}/sse") as response:
                # Read the first data line which contains the session URL
                async for line in response.content:
                    line_text = line.decode('utf-8').strip()
                    
                    if line_text.startswith('data: '):
                        data_str = line_text[6:]
                        
                        # Check if it's a session URL like /message?session_id=...
                        if 'session_id=' in data_str:
                            match = re.search(r'session_id=([a-f0-9-]+)', data_str)
                            if match:
                                self.session_id = match.group(1)
                                self.message_url = f"{self.server_url}{data_str}"
                                logger.debug(f"Got session ID: {self.session_id}")
                                logger.debug(f"Message URL: {self.message_url}")
                                break
                        
                        # Some servers might return the session differently
                        elif data_str.startswith('/message'):
                            self.message_url = f"{self.server_url}{data_str}"
                            logger.debug(f"Message URL: {self.message_url}")
                            break
                            
        except Exception as e:
            logger.error(f"Failed to establish session: {e}")
            raise
    
    def _get_next_id(self) -> int:
        """Get next request ID"""
        self.request_id += 1
        return self.request_id
    
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool on the MCP server"""
        if not self.message_url:
            await self._establish_session()
            if not self.message_url:
                return {"error": {"code": -32603, "message": "Failed to establish session"}}
        
        request_id = self._get_next_id()
        
        request = {
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "jsonrpc": "2.0",
            "id": request_id
        }
        
        try:
            # Send request to the message endpoint
            logger.debug(f"Sending request to {self.message_url}")
            logger.debug(f"Request: {json.dumps(request, indent=2)}")
            
            async with self.session.post(
                self.message_url,
                json=request,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                if response.status == 200:
                    # Read the response
                    result_text = await response.text()
                    
                    # The response might be SSE format or direct JSON
                    if result_text.startswith('data: '):
                        # SSE format - extract the JSON from data: lines
                        lines = result_text.split('\n')
                        for line in lines:
                            if line.startswith('data: ') and line[6:].strip() != '[DONE]':
                                try:
                                    result = json.loads(line[6:])
                                    return self._process_tool_response(result)
                                except json.JSONDecodeError:
                                    continue
                    else:
                        # Direct JSON response
                        try:
                            result = json.loads(result_text)
                            return self._process_tool_response(result)
                        except json.JSONDecodeError:
                            # Maybe it's a number (like in the logs)
                            logger.debug(f"Non-JSON response: {result_text}")
                            
                            # For some responses, we might need to read from SSE stream
                            # Let's try a different approach
                            return await self._call_tool_via_sse(tool_name, arguments)
                else:
                    logger.error(f"Request failed with status {response.status}")
                    return {"error": {"code": -32603, "message": f"HTTP {response.status}"}}
                    
        except asyncio.TimeoutError:
            logger.error("Request timed out")
            return {"error": {"code": -32603, "message": "Request timeout"}}
        except Exception as e:
            logger.error(f"Error calling tool: {e}")
            # Try re-establishing session
            await self._establish_session()
            return {"error": {"code": -32603, "message": str(e)}}
    
    async def _call_tool_via_sse(self, tool_name: str, arguments: dict) -> dict:
        """Alternative method using SSE stream directly"""
        request_id = self._get_next_id()
        
        request = {
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "jsonrpc": "2.0",
            "id": request_id
        }
        
        try:
            # Post to SSE endpoint directly
            async with self.session.post(
                f"{self.server_url}/sse",
                json=request,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                # Read SSE response
                full_response = {}
                async for line in response.content:
                    line_text = line.decode('utf-8').strip()
                    
                    if line_text.startswith('data: '):
                        data_str = line_text[6:]
                        
                        if data_str == '[DONE]':
                            break
                            
                        try:
                            # Try to parse as JSON
                            data = json.loads(data_str)
                            
                            # Check if this is our response
                            if isinstance(data, dict) and data.get('id') == request_id:
                                full_response = data
                                break
                                
                        except json.JSONDecodeError:
                            # Might be a number or session URL
                            if data_str.isdigit():
                                # This is the response ID, next line should have the data
                                continue
                            logger.debug(f"Could not parse: {data_str}")
                
                if full_response:
                    return self._process_tool_response(full_response)
                else:
                    return {"error": {"code": -32603, "message": "No response received"}}
                    
        except Exception as e:
            logger.error(f"SSE call failed: {e}")
            return {"error": {"code": -32603, "message": str(e)}}
    
    def _process_tool_response(self, response: dict) -> dict:
        """Process tool response and handle mixed content types"""
        if "error" in response:
            return response
        
        result = response.get("result", {})
        
        if isinstance(result, dict):
            is_error = result.get("isError", False)
            content = result.get("content", [])
            
            text_parts = []
            image_info = []
            
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type")
                        
                        if item_type == "text":
                            text_content = item.get("text", "")
                            text_parts.append(text_content)
                            
                        elif item_type == "resource_link":
                            name = item.get('name', 'Image')
                            uri = item.get('uri', '')
                            # Note the image but don't include in main output
                            logger.debug(f"Image resource: {name} - {uri}")
                            
            elif isinstance(content, str):
                text_parts.append(content)
            
            # Return just the text content
            combined_text = "\n".join(text_parts)
            
            return {
                "jsonrpc": "2.0",
                "id": response.get("id"),
                "result": {
                    "isError": is_error,
                    "content": combined_text
                }
            }
        
        return response
    
    async def list_tools(self) -> dict:
        """List available tools"""
        # Use the SSE method for listing tools
        return await self._call_tool_via_sse("tools", {"operation": "list"})
    
    async def stop(self):
        """Close the connection"""
        if self.session:
            await self.session.close()
            logger.info("MCP client stopped")

class BridgeServer:
    def __init__(self, mcp_client: HuskyLensMCPClient, host: str = "127.0.0.1", port: int = 8080):
        self.mcp_client = mcp_client
        self.host = host
        self.port = port
        self.app = web.Application()
        self._setup_routes()
        self._setup_cors()
    
    def _setup_cors(self):
        """Setup CORS"""
        async def cors_middleware(app, handler):
            async def middleware_handler(request):
                if request.method == "OPTIONS":
                    response = web.Response()
                else:
                    response = await handler(request)
                response.headers['Access-Control-Allow-Origin'] = '*'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
                return response
            return middleware_handler
        
        self.app.middlewares.append(cors_middleware)
    
    def _setup_routes(self):
        """Setup HTTP routes"""
        self.app.router.add_post('/call', self.handle_tool_call)
        self.app.router.add_get('/tools', self.handle_list_tools)
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_get('/', self.handle_info)
    
    async def handle_info(self, request):
        """Info endpoint"""
        return web.json_response({
            "name": "HuskyLens MCP Bridge",
            "version": "1.0.0",
            "description": "Bridge for HuskyLens2 MCP server",
            "mcp_server": self.mcp_client.server_url,
            "session_id": self.mcp_client.session_id,
            "endpoints": {
                "/": "This info page",
                "/health": "Health check",
                "/tools": "List available tools",
                "/call": "Call a tool (POST)"
            }
        })
    
    async def handle_health(self, request):
        """Health check"""
        return web.json_response({
            "status": "healthy",
            "mcp_server": self.mcp_client.server_url,
            "session_established": self.mcp_client.session_id is not None
        })
    
    async def handle_tool_call(self, request):
        """Handle tool call requests"""
        try:
            data = await request.json()
            tool_name = data.get("tool")
            arguments = data.get("arguments", {})
            
            if not tool_name:
                return web.json_response(
                    {"error": "Missing 'tool' parameter"},
                    status=400
                )
            
            logger.info(f"Calling tool: {tool_name}")
            result = await self.mcp_client.call_tool(tool_name, arguments)
            
            # Check if we have a successful result with content
            if "result" in result and "content" in result["result"]:
                content = result["result"]["content"]
                
                # Try to parse as JSON for prettier output
                try:
                    parsed = json.loads(content)
                    return web.json_response(parsed)
                except (json.JSONDecodeError, TypeError):
                    # Return as plain text if not JSON
                    return web.Response(
                        text=content,
                        content_type='text/plain'
                    )
            
            # Return full result if error or unexpected format
            return web.json_response(result)
            
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON"},
                status=400
            )
        except Exception as e:
            logger.error(f"Error handling tool call: {e}", exc_info=True)
            return web.json_response(
                {"error": str(e)},
                status=500
            )
    
    async def handle_list_tools(self, request):
        """Handle list tools request"""
        try:
            result = await self.mcp_client.list_tools()
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            return web.json_response(
                {"error": str(e)},
                status=500
            )
    
    async def start(self):
        """Start the bridge server"""
        await self.mcp_client.start()
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        logger.info(f"Bridge server running at http://{self.host}:{self.port}")
        logger.info(f"Connected to HuskyLens at {self.mcp_client.server_url}")
        logger.info("\nTest commands:")
        logger.info("  curl http://localhost:8080/health")
        logger.info("  curl -X POST http://localhost:8080/call -H 'Content-Type: application/json' -d '{\"tool\":\"Huskylens2:get_recognition_result\",\"arguments\":{\"operation\":\"get_result\"}}'")
        logger.info("\nUse Ctrl+C to stop")
        
        try:
            await asyncio.Event().wait()
        finally:
            await self.mcp_client.stop()
            await runner.cleanup()

async def main():
    parser = argparse.ArgumentParser(
        description='HuskyLens MCP Bridge - SSE-based bridge for HuskyLens2 camera'
    )
    parser.add_argument(
        '--husky-url',
        default='http://192.168.1.161:3000',
        help='URL of the HuskyLens MCP server (default: http://192.168.1.161:3000)'
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Bridge server host (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='Bridge server port (default: 8080)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create MCP client and bridge
    mcp_client = HuskyLensMCPClient(args.husky_url)
    bridge = BridgeServer(mcp_client, args.host, args.port)
    
    try:
        await bridge.start()
    except KeyboardInterrupt:
        logger.info("Bridge stopped by user")

if __name__ == '__main__':
    asyncio.run(main())