from mcp.server.apps import Apps, ResourceCsp  # noqa: I001


apps = Apps()
__all__ = ["launch_simple_counter"]

RESOURCE_URI = "ui://simple-counter/app.html"
HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      :root {
        color-scheme: light dark;
        font-family: system-ui, sans-serif;
      }
      body {
        display: grid;
        min-height: 220px;
        margin: 0;
        place-items: center;
      }
      main {
        min-width: 240px;
        padding: 24px;
        text-align: center;
      }
      output {
        display: block;
        margin: 12px 0 20px;
        font-size: 3rem;
        font-weight: 700;
      }
      button {
        margin: 4px;
        padding: 8px 14px;
        border: 1px solid currentColor;
        border-radius: 8px;
        font: inherit;
        cursor: pointer;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>Simple Counter</h1>
      <output id="count" aria-live="polite">0</output>
      <button id="decrement" type="button" aria-label="Decrease count">−1</button>
      <button id="increment" type="button" aria-label="Increase count">+1</button>
      <button id="reset" type="button">Reset</button>
    </main>
    <script type="module">
      import { App } from "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@2.0.0/dist/src/app-with-deps.js";

      const countOutput = document.querySelector("#count");
      let count = 0;

      const render = () => {
        countOutput.value = String(count);
        countOutput.textContent = String(count);
      };

      const app = new App({ name: "Simple Counter", version: "1.0.0" });
      app.ontoolresult = (result) => {
        if (!result.isError && Number.isFinite(result.structuredContent?.initial_count)) {
          count = result.structuredContent.initial_count;
          render();
        }
      };

      document.querySelector("#decrement").addEventListener("click", () => {
        count -= 1;
        render();
      });
      document.querySelector("#increment").addEventListener("click", () => {
        count += 1;
        render();
      });
      document.querySelector("#reset").addEventListener("click", () => {
        count = 0;
        render();
      });

      try {
        await app.connect();
      } catch (error) {
        countOutput.textContent = "Unable to connect";
        console.error(error);
      }
    </script>
  </body>
</html>"""


@apps.tool(resource_uri=RESOURCE_URI)
def launch_simple_counter() -> dict[str, str | int]:
    """Open a simple interactive counter with increment, decrement, and reset controls.

    The counter starts at zero and keeps its state only inside the currently open
    app frame. Returns the initial count and a short fallback message for MCP
    clients that do not render Apps. This tool has no external side effects and
    does not persist the count.
    """
    return {
        "title": "Simple Counter",
        "initial_count": 0,
        "message": "Open the app to increment, decrement, or reset the counter.",
    }


apps.add_html_resource(
    RESOURCE_URI,
    HTML,
    title="Simple Counter",
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
)
