# Celsius to Fahrenheit

A compact, stateless MCP App for **°F = °C × 9/5 + 32**.

## Use

Call `celsius_to_fahrenheit(celsius=25)` to open the converter and receive:

```json
{
  "celsius": 25.0,
  "fahrenheit": 77.0,
  "formula": "°F = °C × 9/5 + 32",
  "result": "25 °C = 77 °F"
}
```

Omitting `celsius` starts with **0 °C = 32 °F**. The same structured result is returned as text for clients without App rendering. In the App, enter a Celsius value and press **Enter** or **Convert to Fahrenheit**, or choose a quick temperature. Conversions run through the same MCP tool, not a separate browser formula. A successful interactive result is shared with the conversation using the standard MCP Apps context API; failure to share context does not discard the result.

- Finite numeric inputs only; booleans, strings, null, NaN and infinities are rejected.
- Negative and decimal values are supported. As a mathematical scale conversion, it does not impose a physical absolute-zero bound.
- Common decimals use decimal arithmetic before returning a float64 number. Very large results outside float64 range return an explicit error; values beyond float64 precision are not arbitrary-precision measurements.
- Pending requests disable controls; edits clear stale results; errors allow retry.
- Responsive light/dark styles follow host theme changes. Labels, focus indicators, keyboard submission and live status/result announcements are included.

## MCP and privacy

Exactly one model-facing tool, `celsius_to_fahrenheit`, and one resource, `ui://celsius-to-fahrenheit/app.html`, are registered on the supplied server. No additional App Handler is needed because conversion is safe for both App and model use. The tool is annotated read-only, non-destructive, idempotent and closed-world.

The resource loads the adjacent HTML and inlines the adjacent JavaScript. The **official MCP Apps SDK 2.0.0** is imported from `https://cdn.jsdelivr.net`, the sole CSP resource origin. The App has no direct network/connect origins; tool calls use the host bridge. SDK loading requires CDN access. Existing ToolForge authentication is unchanged. No credentials, conversion history, browser storage, database, or external calculation service is used. MCP clients may retain their ordinary conversation/tool history independently.

## Test

From the repository root:

```bash
uv sync --all-packages
uv run --no-sync python -m unittest discover -s tests -p 'test_celsius_to_fahrenheit.py' -v
node --check src/catalog_app/tools/celsius_to_fahrenheit/app.js
uv run --no-sync python -m unittest discover -s tests -p 'test_celsius_browser.py' -v
```

The Python contract suite exercises the real MCP client, argument/output schemas, useful fallback, registration/resource metadata, module-relative assets, reference conversions, finite validation, overflow, and no-I/O conversion behavior.

The browser suite requires `agent-browser` and the declared SDK CDN. It starts an ephemeral **loopback-only test host**, uses its own named Chromium session, loads the unchanged production App and official SDK, and forwards bridge calls to the actual Python MCP converter. Host errors/delays are injected only in the isolated fixture. The test host and browser are closed on completion. Screenshots/audit data go to Git-ignored artifacts.

**Verification boundary:** this local bridge suite is not ToolForge's real **Open App / View App** host UI. Publication must additionally be checked against the live applied commit and registered resource. Actual native host controls require a reachable authenticated ToolForge UI; do not infer their acceptance from a local fixture.

No Python dependency or server-wide configuration changes are required.
