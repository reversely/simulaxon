"""HTTP and MCP surfaces over the one tool registry (implementation spec §7).

HTTP, for the browser panels:
  GET  /tools                     every tool with its resource, verb and whether it writes a step
  POST /tools/{name}              JSON body of arguments; header X-Actor: person or agent
  GET  /events (WebSocket)        one message per store write, so panels re-render
MCP, for the agent: the same registry, each tool exposed under the same name with actor "agent".
"""
from __future__ import annotations
import asyncio, dataclasses, json
from fastapi import FastAPI, Header, HTTPException, WebSocket
from .store import Store, Conflict, Row
from .tools import Tools, NeedsPerson
from .script import ScriptError


def _plain(x):
    if isinstance(x, Row): return dataclasses.asdict(x)
    if isinstance(x, list): return [_plain(i) for i in x]
    return x


def create_app(store: Store | None = None) -> FastAPI:
    tools = Tools(store or Store())
    app = FastAPI(title='Simulaxon')
    listeners: set[asyncio.Queue] = set()

    @app.get('/tools')
    def list_tools():
        import inspect
        def sig(fn):
            ps = [p for n, p in inspect.signature(fn).parameters.items() if n not in ('step', 'actor')]
            return ', '.join(n.name + ('' if n.default is inspect.Parameter.empty else f'={n.default!r}') for n in ps)
        return [{'name': t.name, 'resource': t.resource, 'verb': t.verb, 'writes_step': t.writes_project and t.verb not in ('get', 'list', 'search', 'query'),
                 'person_only': t.person_only, 'doc': (t.fn.__doc__ or '').strip(), 'arguments': sig(t.fn)} for t in tools.registry.values()]

    @app.post('/tools/{name}')
    async def call_tool(name: str, body: dict, x_actor: str = Header('person')):
        if name not in tools.registry: raise HTTPException(404, f'no tool {name}')
        try:
            out = tools.call(name, x_actor, **body)
        except NeedsPerson as e: raise HTTPException(403, {'needs_person': str(e)})
        except Conflict as e: raise HTTPException(409, {'conflict': str(e)})
        except (ScriptError, ValueError, KeyError, TypeError) as e: raise HTTPException(422, {'invalid': str(e)})
        t = tools.registry[name]
        if (t.writes_project and t.verb not in ('get', 'list', 'search', 'query')) or name == 'step_undo':   # reads never broadcast, so panels never loop
            msg = json.dumps({'tool': name, 'actor': x_actor})
            for q in list(listeners): q.put_nowait(msg)
        return {'result': _plain(out)}

    @app.websocket('/events')
    async def events(ws: WebSocket):
        await ws.accept(); q: asyncio.Queue = asyncio.Queue(); listeners.add(q)
        try:
            while True: await ws.send_text(await q.get())
        finally:
            listeners.discard(q)

    loop_ref = {}

    @app.on_event('startup')
    async def _keep_loop():
        loop_ref['loop'] = asyncio.get_running_loop()

    def broadcast(msg: dict):
        """Send an event from any thread, such as a preview job finishing."""
        loop = loop_ref.get('loop')
        if loop:
            for q in list(listeners): loop.call_soon_threadsafe(q.put_nowait, json.dumps(msg))

    app.state.broadcast = broadcast
    app.state.tools = tools
    return app


def create_mcp(tools: Tools):
    """MCP server exposing the same registry to the agent."""
    try:
        from mcp.server.mcpserver import MCPServer as Server   # mcp 2.x
    except ImportError:
        from mcp.server.fastmcp import FastMCP as Server       # mcp 1.x
    mcp = Server('simulaxon')
    for t in tools.registry.values():
        def make(name):
            def run(arguments: dict) -> str:
                try:
                    return json.dumps({'result': _plain(tools.call(name, 'agent', **arguments))}, default=str)
                except NeedsPerson as e:
                    return json.dumps({'needs_person': str(e)})
                except Conflict as e:
                    return json.dumps({'conflict': str(e)})
            run.__name__ = name; return run
        mcp.add_tool(make(t.name), name=t.name, description=(t.fn.__doc__ or t.name).strip())
    return mcp
