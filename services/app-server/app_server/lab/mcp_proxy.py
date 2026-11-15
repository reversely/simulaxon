"""MCP server for the agent, forwarding every tool to the running app over HTTP with actor "agent".

The app holds the store, so the agent and the panels act on the same rows and every agent call writes a step and an
event, which moves the same controls on screen. Usage (by the agent runtime): python -m app_server.lab.mcp_proxy [BASE_URL]
"""
from __future__ import annotations
import json, sys, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8790'


def _http(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json', 'X-Actor': 'agent'})
    try:
        with urllib.request.urlopen(req, timeout=600) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'detail': json.loads(e.read() or b'{}').get('detail')}


def main():
    try:
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:
        from mcp.server.fastmcp import FastMCP as Server
    mcp = Server('vcl')
    from .planner_agent import describe, offered
    for t in _http('GET', '/tools'):
        if not offered(t): continue
        def make(name):
            def run(arguments: dict | None = None) -> str:
                return json.dumps(_http('POST', f'/tools/{name}', arguments or {}), default=str)[:60000]
            run.__name__ = name; return run
        mcp.add_tool(make(t['name']), name=t['name'], description=describe(t) + ' Pass them as an object in "arguments".')
    mcp.run()


if __name__ == '__main__':
    main()
