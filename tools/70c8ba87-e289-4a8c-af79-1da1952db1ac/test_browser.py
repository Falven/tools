"""Real Chromium checks with the official MCP App/host bridge and Python SDK.

Only synthetic identities are used. The host below is a loopback-only test
fixture, never a production authentication endpoint. No test code is imported
by tool.py. Run from the workspace's uv environment with Playwright installed.
"""

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from mcp.server.mcpserver import MCPServer
from playwright.async_api import async_playwright, expect

import tool
from test_tool import caller


HOST = """<!doctype html><html><head><meta name="viewport"
content="width=device-width, initial-scale=1"><style>
html,body{margin:0;background:#0b100f}iframe{display:block;width:100%;height:900px;border:0}
</style></head><body><iframe id="app" title="Neon Snake test"
sandbox="allow-scripts"></iframe><script type="module">
import { AppBridge, PostMessageTransport } from
"https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@2.0.0/dist/src/app-bridge.js/+esm";
const frame = document.querySelector("#app");
const bridge = new AppBridge(null, {name:"Synthetic test host",version:"1.0.0"},
  {serverTools:{},logging:{}},
  {hostContext:{theme:"dark",displayMode:"inline",availableDisplayModes:["inline"],
    locale:"en-US",platform:"web"}});
window.modelContexts = [];
window.dropNextFinish = false;
bridge.oncalltool = async params => {
  const result = await window.testCallTool(params);
  if (params.name === "neon_snake_finish" && window.dropNextFinish) {
    window.dropNextFinish = false;
    throw new Error("Synthetic lost response after server commit");
  }
  return result;
};
bridge.onupdatemodelcontext = async params => {
  window.modelContexts.push(params);
  return {};
};
bridge.onsizechange = ({height}) => {
  if (height) frame.style.height = Math.ceil(height) + "px";
};
bridge.oninitialized = async () => {
  await bridge.sendToolInput({arguments:{}});
  await bridge.sendToolResult(await window.testCallTool({name:"new_tool",arguments:{}}));
};
await bridge.connect(new PostMessageTransport(frame.contentWindow, frame.contentWindow));
frame.src = "/app";
window.bridge = bridge;
</script></body></html>"""


class FixtureHTTP(BaseHTTPRequestHandler):
    def do_GET(self):
        body = tool.HTML if self.path == "/app" else HOST
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if self.path == "/app":
            # The app cannot fetch our host or access storage. All server work
            # must travel through the official bridge and callServerTool.
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'unsafe-inline' https://cdn.jsdelivr.net; "
                             "style-src 'unsafe-inline'; img-src data:; connect-src 'none'; "
                             "font-src 'none'; base-uri 'none'; form-action 'none'")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


class BrowserChecks:
    def __init__(self, origin, artifacts):
        self.origin, self.artifacts = origin, artifacts
        self.server = MCPServer("Synthetic browser test", extensions=[tool.apps])
        self.calls, self.errors = [], []
        self.identity = {}
        self.seed = next(seed for seed in range(1, 5000)
                         if tool._Game(seed).food == (7, 9)
                         and tool._replay(seed, "1" * 12).score == 10)

    async def rpc(self, params):
        self.calls.append(params)
        with caller(**self.identity), patch.object(tool.secrets, "randbelow", return_value=self.seed - 1):
            result = await self.server.call_tool(params["name"], params.get("arguments") or {})
        return result.model_dump(by_alias=True, exclude_none=True)

    async def open(self, page):
        await page.expose_function("testCallTool", self.rpc)
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        await page.goto(self.origin, wait_until="domcontentloaded")
        await page.wait_for_selector("#app")
        app = page.frame_locator("#app")
        await expect(app.locator("#start")).to_be_enabled(timeout=30000)
        return app

    async def state(self, app, value):
        if value in ("running", "over"):
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                current = await app.locator("#stage").get_attribute("data-state")
                if current == value:
                    return
                if current == "paused" and "display was busy" in await app.locator("#pause-reason").inner_text():
                    # Software WebGL can compile a shader for >500ms on this
                    # one-CPU runner. Use the real Resume control, never change
                    # game clocks, traces, scores, or the server's validation.
                    print("CHECK software-GPU stall correctly auto-paused; resuming through the UI", flush=True)
                    await app.locator("#resume").click()
                await asyncio.sleep(.07)
        await expect(app.locator("#stage")).to_have_attribute("data-state", value, timeout=15000)

    async def layout(self, page, app, panel="ready-panel"):
        dimensions = await app.locator("body").evaluate("""(body, panelId) => {
          const stage = document.querySelector("#stage").getBoundingClientRect();
          const panel = document.getElementById(panelId).getBoundingClientRect();
          return {width:innerWidth,scrollWidth:body.scrollWidth,
            stage:{top:stage.top,bottom:stage.bottom,left:stage.left,right:stage.right},
            panel:{top:panel.top,bottom:panel.bottom,left:panel.left,right:panel.right}};
        }""", panel)
        assert dimensions["scrollWidth"] <= dimensions["width"], dimensions
        s, p = dimensions["stage"], dimensions["panel"]
        assert p["top"] >= s["top"] + 30, dimensions
        assert p["bottom"] <= s["bottom"] - 22, dimensions
        assert p["left"] >= s["left"] and p["right"] <= s["right"], dimensions
        await page.screenshot(path=str(self.artifacts / f"{dimensions['width']}-{panel}.png"),
                              full_page=True)
        return dimensions

    async def desktop(self, browser):
        context = await browser.new_context(viewport={"width":1100, "height":950}, device_scale_factor=1)
        page = await context.new_page()
        app = await self.open(page)
        await expect(app.locator("#stage")).to_have_attribute("data-renderer", "three")
        await expect(app.locator("#player-name")).to_have_text("Fixture One")
        await expect(app.locator("#player-email")).to_have_text("f•••@example.test")
        assert await app.locator("#scene canvas").evaluate("(c) => !!c.getContext('webgl2')")
        await self.layout(page, app)
        await expect(app.locator("#leaderboard li")).to_have_count(0)
        await app.locator("#start").click()
        await self.state(app, "countdown")
        await app.locator("#stage").press("ArrowLeft")  # Opposite turn must be ignored.
        await app.locator("#stage").press("Space")
        await self.state(app, "paused")
        timer = await app.locator("#timer").inner_text()
        await page.wait_for_timeout(400)
        await expect(app.locator("#timer")).to_have_text(timer)
        await self.layout(page, app, "pause-panel")
        await app.locator("#resume").click()
        await self.state(app, "over")
        await expect(app.locator("#save-state")).to_contain_text("Saved automatically")
        await expect(app.locator("#final-score")).to_have_text("10")
        await expect(app.locator("#leaderboard li")).to_have_count(1)
        await expect(app.locator("#personal-runs")).to_have_text("1")
        await expect(app.locator("#best")).to_have_text("0010")
        await self.layout(page, app, "over-panel")
        finishes = [c for c in self.calls if c["name"] == "neon_snake_finish"]
        assert len(finishes) == 1 and finishes[0]["arguments"]["directions"] == "1" * 12, finishes
        assert "fixture.one@example.test" not in await app.locator("body").inner_text()
        await page.wait_for_function("window.modelContexts.length === 1")
        model = await page.evaluate("window.modelContexts")
        assert "example.test" not in json.dumps(model) and model[0]["structuredContent"]["score"] == 10
        await app.locator("#scope-mine").click()
        await expect(app.locator("#scope-mine")).to_have_attribute("aria-pressed", "true")
        await expect(app.locator("#leaderboard .rank")).to_have_text("01")
        print("PASS desktop: real Three.js/WebGL, countdown, movement, reversal guard, pause/resume, "
              "automatic server-verified score, account name, masked e-mail, model context")

        # The server commits normally, but the host simulates losing the response.
        # Retrying must return confirmation, not insert a duplicate score.
        await page.evaluate("window.dropNextFinish = true")
        await app.locator("#again").click()
        await self.state(app, "countdown")
        await self.state(app, "over")
        await expect(app.locator("#retry-save")).to_be_visible()
        await expect(app.locator("#save-state")).to_contain_text("Not saved yet")
        await self.layout(page, app, "over-panel")
        await app.locator("#retry-save").click()
        await expect(app.locator("#save-state")).to_contain_text("Saved automatically")
        await expect(app.locator("#personal-runs")).to_have_text("2")
        await expect(app.locator("#leaderboard li")).to_have_count(2)
        finish_calls = [c for c in self.calls if c["name"] == "neon_snake_finish"]
        assert len(finish_calls) == 3, finish_calls
        assert finish_calls[-1]["arguments"] == finish_calls[-2]["arguments"]
        print("PASS interrupted score response: visible retry, idempotent save, exactly two recorded runs")

        await page.reload()
        app = page.frame_locator("#app")
        await expect(app.locator("#personal-runs")).to_have_text("2", timeout=30000)
        await expect(app.locator("#leaderboard li")).to_have_count(2)
        await expect(app.locator("#start")).to_be_enabled()
        starts_before = len([c for c in self.calls if c["name"] == "neon_snake_begin"])
        finishes_before = len([c for c in self.calls if c["name"] == "neon_snake_finish"])
        await app.locator("#practice").click()
        await self.state(app, "countdown")
        await app.locator("#stage").press("w")
        await self.state(app, "over")
        await expect(app.locator("#save-state")).to_contain_text("Practice run")
        assert len([c for c in self.calls if c["name"] == "neon_snake_begin"]) == starts_before
        assert len([c for c in self.calls if c["name"] == "neon_snake_finish"]) == finishes_before
        print("PASS reload persistence, WASD input, practice mode never starts/saves a ranked run")

        await app.locator("#data-button").click()
        await expect(app.locator("#data-dialog")).to_be_visible()
        await app.locator("#delete-data").click()
        await expect(app.locator("#data-dialog")).to_be_visible()
        assert not any(c["name"] == "neon_snake_forget" for c in self.calls)
        await app.locator("#confirm-delete").check()
        await app.locator("#delete-data").click()
        await expect(app.locator("#data-dialog")).not_to_be_visible()
        await expect(app.locator("#personal-runs")).to_have_text("0")
        await expect(app.locator("#leaderboard li")).to_have_count(0)
        print("PASS privacy: confirmed deletion removes the fixture's profile and runs")
        await context.close()

    async def mobile(self, browser):
        self.identity = {"oid":"mobile-fixture", "name":"", "email":""}
        context = await browser.new_context(viewport={"width":390,"height":844}, device_scale_factor=1,
                                            is_mobile=True, has_touch=True, reduced_motion="reduce")
        page = await context.new_page()
        app = await self.open(page)
        await expect(app.locator("#stage")).to_have_attribute("data-renderer", "three")
        await self.layout(page, app)
        await app.locator("#start").tap()
        await expect(app.locator("#profile-dialog")).to_be_visible()
        await app.locator("#profile-name").fill("Mobile Fixture")
        await app.locator("#profile-email").fill("mobile.fixture@example.test")
        await app.locator("#save-profile").tap()
        await self.state(app, "countdown")
        await app.locator('[data-direction="0"]').tap()
        await self.state(app, "over")
        await expect(app.locator("#save-state")).to_contain_text("Saved automatically")
        await expect(app.locator("#player-name")).to_have_text("Mobile Fixture")
        await expect(app.locator("#player-email")).to_have_text("m•••@example.test")
        latest = [c for c in self.calls if c["name"] == "neon_snake_finish"][-1]
        assert latest["arguments"]["directions"] == "0" * 10, latest
        await self.layout(page, app, "over-panel")
        await app.locator("#back-to-menu").tap()
        await page.set_viewport_size({"width":320, "height":740})
        await self.layout(page, app)
        await app.locator("#help-button").tap()
        await expect(app.locator("#help-dialog")).to_be_visible()
        await app.get_by_role("button", name="Close instructions").tap()
        # The footer is below the phone viewport in an auto-sized iframe.
        # Its modal must be placed in the currently visible clipped area.
        await app.locator("#data-button").tap()
        await expect(app.locator("#data-dialog")).to_be_visible()
        await app.get_by_role("button", name="Close privacy details").tap()
        print("PASS mobile: 390/320px layout, reduced motion, missing-claims profile form, touch direction pad")
        await context.close()

    async def compatibility(self, browser):
        context = await browser.new_context(viewport={"width":800,"height":900})
        page = await context.new_page()
        await page.route("**/npm/three@*/**", lambda route: route.abort())
        # Top-level HTML has no bridge and must remain explicitly practice-only.
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        await page.goto(self.origin + "/app")
        await expect(page.locator("#stage")).to_have_attribute("data-renderer", "compatibility", timeout=15000)
        await expect(page.locator("#start-label")).to_have_text("Play practice")
        await page.locator("#start").click()
        await self.state(page, "over")
        await expect(page.locator("#save-state")).to_contain_text("Practice run")
        await page.screenshot(path=str(self.artifacts / "compatibility.png"), full_page=True)
        print("PASS CDN/WebGL-unavailable fallback: playable 2D, explicit practice-only guest mode")
        await context.close()


async def main():
    artifacts = tool.ASSETS / ".test-artifacts"
    artifacts.mkdir(exist_ok=True)
    http = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHTTP)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="browser-", dir=artifacts) as directory, \
                patch.dict(os.environ, {"NEON_SNAKE_DB_PATH": str(Path(directory) / "scores.sqlite3")}):
            checks = BrowserChecks(f"http://127.0.0.1:{http.server_port}", artifacts)
            async with async_playwright() as playwright:
                # The development container has 1 CPU and 1.2 GB RAM. Separate
                # low-memory browser launches avoid an OOM, not game validation.
                suites = {"desktop": checks.desktop, "mobile": checks.mobile, "compatibility": checks.compatibility}
                selected = sys.argv[1:] or list(suites)
                for name in selected:
                    check = suites[name]
                    print(f"CHECK browser suite: {name}", flush=True)
                    browser = await playwright.chromium.launch(args=[
                        "--no-sandbox", "--no-zygote", "--single-process",
                        "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                        "--num-raster-threads=1", "--js-flags=--max-old-space-size=96",
                    ])
                    try:
                        await check(browser)
                    finally:
                        await browser.close()
                assert not checks.errors, checks.errors
                print("PASS no uncaught browser JavaScript errors; synthetic database removed after checks")
    finally:
        http.shutdown()
        http.server_close()


if __name__ == "__main__":
    asyncio.run(main())