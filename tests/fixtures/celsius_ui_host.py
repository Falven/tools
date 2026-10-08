"""Loopback-only QA host using the real converter MCP server, not ToolForge.

The production App/official SDK are unchanged. This fixture supplies the host
postMessage bridge and forwards tools/call to a real in-process MCP client.
Fault injection lives ONLY in the fixture; no test operation is published.
"""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from mcp.client import Client
from mcp.server import MCPServer
from mcp.server.apps import Apps

from tests.fixtures.catalog import register_catalog_tool

from catalog_app.tools import celsius_to_fahrenheit as converter

HOST = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Converter local QA host</title>
<style>body {margin:0;font:12px system-ui;background:#f4f7fb;color:#17263f} header {padding:8px 16px} iframe {display:block;width:100%;height:850px;border:0}</style>
</head><body><header>Local MCP App test fixture — not the ToolForge host</header>
<iframe id="qa-app" title="Celsius to Fahrenheit App"></iframe>
<script>
const frame = document.querySelector('#qa-app');
const fixture = window.fixture = {
  calls: [], contexts: [], errors: [], pending: [], ready: false,
  failNext: false, failContext: false, invalidNext: false, textOnly: false, delay: false,
};
const send = data => frame.contentWindow.postMessage({jsonrpc: '2.0', ...data}, location.origin);
fixture.notify = (method, params) => send({method, params});
fixture.release = () => { for (const respond of fixture.pending.splice(0)) respond(); };
frame.addEventListener('load', () => {
  frame.contentWindow.addEventListener('error', event => fixture.errors.push(event.message));
  frame.contentWindow.addEventListener('unhandledrejection', event => fixture.errors.push(String(event.reason)));
});
const call = async params => {
  const response = await fetch('/call', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(params)});
  if (!response.ok) throw new Error('Local fixture HTTP ' + response.status);
  return response.json();
};
window.addEventListener('message', async event => {
  if (event.source !== frame.contentWindow || event.origin !== location.origin || event.data?.jsonrpc !== '2.0') return;
  const {id, method, params = {}} = event.data;
  const reply = result => send({id, result});
  if (method === 'ui/initialize') {
    reply({protocolVersion: params.protocolVersion,
      hostInfo: {name: 'Isolated converter QA host', version: '1.0.0'},
      hostCapabilities: {serverTools: {}, logging: {}},
      hostContext: {theme: 'light', displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen'], locale: 'en-US'},
    });
  } else if (method === 'ui/notifications/initialized') {
    const result = await call({name: 'celsius_to_fahrenheit', arguments: {celsius: 25}});
    fixture.notify('ui/notifications/tool-input', {arguments: {celsius: 25}});
    fixture.notify('ui/notifications/tool-result', result);
    fixture.ready = true;
  } else if (method === 'ui/update-model-context') {
    if (fixture.failContext) send({id, error: {code: -32000, message: 'QA context update failure'}});
    else { fixture.contexts.push(params); reply({}); }
  } else if (method === 'tools/call') {
    fixture.calls.push(params);
    let result;
    if (fixture.failNext) {
      fixture.failNext = false;
      result = {isError: true, content: [{type: 'text', text: 'QA simulated server failure. Try again.'}]};
    } else if (fixture.invalidNext) {
      fixture.invalidNext = false;
      result = {structuredContent: {fahrenheit: 'not a number'}, content: []};
    } else {
      result = await call(params);
      if (fixture.textOnly) delete result.structuredContent;
    }
    if (fixture.delay) fixture.pending.push(() => reply(result));
    else reply(result);
  } else if (method === 'ping') reply({});
  else if (id !== undefined) send({id, error: {code: -32601, message: 'Unsupported QA host method: ' + method}});
});
frame.src = '/app';
</script></body></html>'''


def start_host():
    server = MCPServer("converter-browser-qa", extensions=[Apps()])
    register_catalog_tool(server, "celsius_to_fahrenheit")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_bytes(self, content, content_type, *, app=False):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            if app:
                self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'unsafe-inline'; connect-src 'none'; frame-ancestors 'self'")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.path == "/":
                self.send_bytes(HOST.encode(), "text/html; charset=utf-8")
            elif self.path == "/app":
                self.send_bytes(converter._app_html().encode(), "text/html; charset=utf-8", app=True)
            elif self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/call":
                self.send_error(404)
                return
            origin = self.headers.get("Origin")
            if origin != f"http://127.0.0.1:{self.server.server_port}":
                self.send_error(403)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                self.send_error(400)
                return
            params = json.loads(self.rfile.read(length))
            if params.get("name") != "celsius_to_fahrenheit":
                self.send_error(400)
                return

            async def invoke():
                async with Client(server) as client:
                    return await client.call_tool(params["name"], params.get("arguments", {}))

            result = asyncio.run(invoke())
            # Match MCP transport serialization: optional fields are omitted,
            # not null (the official browser SDK correctly rejects null metadata).
            content = result.model_dump_json(by_alias=True, exclude_none=True).encode()
            self.send_bytes(content, "application/json")

    host = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    return host, thread
