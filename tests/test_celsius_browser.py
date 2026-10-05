"""Real Chromium + official Apps SDK + real Python MCP conversion smoke tests.

The outer host is an isolated local fixture, NOT ToolForge's Open App/View App.
Requires agent-browser and access to the App's declared pinned SDK CDN.
Run: uv run --no-sync python -m unittest discover -s tests -p 'test_celsius_browser.py' -v
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from fixtures.celsius_ui_host import start_host

ROOT = Path(__file__).resolve().parents[1]
DOC = "document.querySelector('#qa-app').contentDocument"


@unittest.skipUnless(shutil.which("agent-browser"), "agent-browser is required")
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        session = subprocess.run(
            ["agent-browser", "session", "id", "--scope", "worktree", "--prefix", "celsius-qa"],
            cwd=ROOT, text=True, check=True, capture_output=True,
        ).stdout.strip()
        cls.env = {**os.environ, "AGENT_BROWSER_SESSION": session}
        cls.host, cls.thread = start_host()
        cls.url = f"http://127.0.0.1:{cls.host.server_port}/"
        cls.addClassCleanup(cls.cleanup)

    @classmethod
    def browser(cls, *arguments, script=None):
        result = subprocess.run(
            ["agent-browser", *arguments, "--json"], cwd=ROOT, env=cls.env,
            input=script, capture_output=True, text=True, timeout=45,
        )
        if result.returncode:
            diagnostic = subprocess.run(
                ["agent-browser", "doctor", "--offline", "--quick"],
                cwd=ROOT, env=cls.env, capture_output=True, text=True, timeout=45,
            )
            raise AssertionError(f"Browser exited {result.returncode}: {result.stdout}\n{result.stderr}\n{diagnostic.stdout}")
        response = json.loads(result.stdout)
        if not response["success"]:
            raise AssertionError(response)
        return response["data"]

    @classmethod
    def cleanup(cls):
        try:
            cls.browser("close")
        finally:
            cls.host.shutdown()
            cls.host.server_close()
            cls.thread.join(timeout=5)

    def evaluate(self, script):
        return self.browser("eval", "--stdin", script=script)["result"]

    def wait(self, condition):
        self.browser("wait", "--fn", condition)

    def setUp(self):
        self.browser("set", "viewport", "880", "920")
        self.browser("open", self.url)
        self.wait(f"window.fixture?.ready && {DOC}?.querySelector('#fahrenheit')?.textContent === '77' && !{DOC}.querySelector('#celsius').disabled")

    def tearDown(self):
        self.browser("frame", "main")
        self.assertEqual(self.evaluate("fixture.errors"), [])

    def convert(self, value, *, enter=False):
        self.browser("frame", "#qa-app")
        self.browser("fill", "#celsius", value)
        if enter:
            self.browser("press", "Enter")
        else:
            self.browser("click", "#convert")
        self.browser("frame", "main")
        self.wait(f"{DOC}.querySelector('#converter').getAttribute('aria-busy') === 'false'")

    def assert_result(self, value):
        self.wait(f"{DOC}.querySelector('#fahrenheit').textContent === {json.dumps(value)}")
        self.assertEqual(self.evaluate(f"{DOC}.querySelector('#status').dataset.error"), "false")

    def test_opening_input_and_result_are_delivered_after_handshake(self):
        self.assertEqual(self.evaluate(f"{DOC}.querySelector('#celsius').value"), "25")
        self.assert_result("77")
        self.assertEqual(self.evaluate("fixture.calls.length"), 0)
        self.assertEqual(self.evaluate("fixture.contexts.length"), 0)

    def test_negative_decimal_and_enter_submit_real_mcp_calls(self):
        for value, expected in [("-40", "-40"), ("37", "98.6"), ("12.5", "54.5"), ("-273.15", "-459.67")]:
            with self.subTest(value=value):
                self.convert(value, enter=True)
                self.assert_result(expected)
                context = self.evaluate("fixture.contexts.at(-1).structuredContent")
                self.assertEqual(context["fahrenheit"], float(expected))
        self.assertEqual(self.evaluate("fixture.calls.length"), 4)

    def test_quick_temperature_buttons(self):
        for value, expected in [("0", "32"), ("20", "68"), ("100", "212")]:
            self.browser("frame", "#qa-app")
            self.browser("click", f'[data-celsius="{value}"]')
            self.browser("frame", "main")
            self.assert_result(expected)
            self.wait(f"!{DOC}.querySelector('#celsius').disabled")

    def test_empty_input_is_rejected_locally_without_stale_result(self):
        self.convert("")
        self.assertEqual(self.evaluate("fixture.calls.length"), 0)
        self.assertEqual(self.evaluate(f"{DOC}.querySelector('#fahrenheit').textContent"), "—")
        self.assertEqual(self.evaluate(f"{DOC}.querySelector('#celsius').getAttribute('aria-invalid')"), "true")
        self.assertIn("finite Celsius number", self.evaluate(f"{DOC}.querySelector('#status').textContent"))

    def test_overflow_error_and_recovery(self):
        self.convert("1.7e308")
        self.assertIn("supported numeric range", self.evaluate(f"{DOC}.querySelector('#status').textContent"))
        self.assertEqual(self.evaluate(f"{DOC}.querySelector('#fahrenheit').textContent"), "—")
        self.convert("25")
        self.assert_result("77")

    def test_server_and_malformed_results_are_recoverable(self):
        for flag, expected in [("failNext", "QA simulated server failure"), ("invalidNext", "invalid result")]:
            self.evaluate(f"fixture.{flag} = true")
            self.convert("30")
            self.assertIn(expected, self.evaluate(f"{DOC}.querySelector('#status').textContent"))
            self.assertEqual(self.evaluate(f"{DOC}.querySelector('#fahrenheit').textContent"), "—")
            self.convert("37")
            self.assert_result("98.6")

    def test_context_failure_preserves_successful_conversion(self):
        self.evaluate("fixture.failContext = true")
        self.convert("37")
        self.assert_result("98.6")
        self.assertIn("could not share", self.evaluate(f"{DOC}.querySelector('#status').textContent"))

    def test_text_only_mcp_result_is_supported(self):
        self.evaluate("fixture.textOnly = true")
        self.convert("100")
        self.assert_result("212")

    def test_busy_state_prevents_duplicate_requests(self):
        self.evaluate("fixture.delay = true")
        self.browser("frame", "#qa-app")
        self.browser("fill", "#celsius", "37")
        self.browser("click", "#convert")
        self.browser("frame", "main")
        self.wait("fixture.pending.length === 1")
        self.assertTrue(self.evaluate(f"[...{DOC}.querySelectorAll('input, button')].every(control => control.disabled)"))
        self.assertEqual(self.evaluate("fixture.calls.length"), 1)
        self.evaluate("fixture.release()")
        self.assert_result("98.6")
        self.wait(f"!{DOC}.querySelector('#celsius').disabled")

    def test_late_opening_result_does_not_overwrite_user_edit(self):
        self.browser("frame", "#qa-app")
        self.browser("fill", "#celsius", "42")
        self.browser("frame", "main")
        self.evaluate("""fixture.notify('ui/notifications/tool-input', {arguments: {celsius: 0}});
fixture.notify('ui/notifications/tool-result', {content: [], structuredContent: {celsius: 0, fahrenheit: 32, result: '0 °C = 32 °F'}});""")
        self.assertEqual(self.evaluate(f"{DOC}.querySelector('#celsius').value"), "42")
        self.assertEqual(self.evaluate(f"{DOC}.querySelector('#fahrenheit').textContent"), "—")
        self.convert("42")
        self.assert_result("107.6")

    def test_responsive_layout_dark_theme_and_accessibility(self):
        for width in [880, 375, 320]:
            self.browser("set", "viewport", str(width), "920")
            self.assertTrue(self.evaluate(f"{DOC}.documentElement.scrollWidth <= document.querySelector('#qa-app').clientWidth"))
        self.evaluate("fixture.notify('ui/notifications/host-context-changed', {theme: 'dark'})")
        self.wait(f"{DOC}.documentElement.dataset.theme === 'dark'")
        self.assert_result("77")
        audit = self.browser("a11y", "--tags", "wcag2a,wcag2aa")
        (ROOT / "artifacts").mkdir(exist_ok=True)
        (ROOT / "artifacts/celsius-a11y.json").write_text(json.dumps(audit, indent=2))
        # The CLI nests the axe result under report on current versions; accept
        # a direct axe result too, while still failing if no audit was returned.
        report = audit.get("report", audit)
        self.assertIn("violations", report)
        self.assertEqual(report["violations"], [])
        self.evaluate("fixture.notify('ui/notifications/host-context-changed', {theme: 'light'})")
        self.wait(f"{DOC}.documentElement.dataset.theme === 'light'")
        self.browser("set", "viewport", "720", "920")
        self.browser("screenshot", str(ROOT / "artifacts/celsius-to-fahrenheit.png"))


if __name__ == "__main__":
    unittest.main()
