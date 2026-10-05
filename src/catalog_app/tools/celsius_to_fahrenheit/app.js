// The official, version-pinned SDK handles the MCP Apps bridge.
const form = document.querySelector("#converter");
const input = document.querySelector("#celsius");
const button = document.querySelector("#convert");
const fahrenheit = document.querySelector("#fahrenheit");
const equation = document.querySelector("#equation");
const status = document.querySelector("#status");
const controls = [...form.querySelectorAll("input, button")];
let app;
let connected = false;
let busy = false;
let interacted = false;

function setControls() {
  for (const control of controls) control.disabled = !connected || busy;
  form.setAttribute("aria-busy", String(busy));
  button.textContent = busy ? "Converting…" : "Convert to Fahrenheit →";
}

function message(text, error = false) {
  status.textContent = text;
  status.dataset.error = String(error);
}

function clearResult() {
  fahrenheit.textContent = "—";
  equation.textContent = "Convert to see the result.";
}

function showResult(result) {
  if (result.isError) {
    const detail = result.content?.filter((item) => item.type === "text").map((item) => item.text).join(" ");
    throw new Error(detail || "Conversion failed. Please try again.");
  }
  let data = result.structuredContent;
  if (!data) {
    const text = result.content?.find((item) => item.type === "text")?.text;
    try { data = JSON.parse(text); } catch { /* Report an invalid host result below. */ }
  }
  if (!data || !Number.isFinite(data.celsius) || !Number.isFinite(data.fahrenheit) || typeof data.result !== "string") {
    throw new Error("The host returned an invalid result. Please try converting again.");
  }
  input.value = String(data.celsius);
  fahrenheit.textContent = String(data.fahrenheit);
  equation.textContent = data.result;
  input.removeAttribute("aria-invalid");
  message("Converted successfully.");
  return data;
}

function applyTheme(context) {
  if (context?.theme === "light" || context?.theme === "dark") {
    document.documentElement.dataset.theme = context.theme;
  }
}

async function convert() {
  if (!connected || busy) return;
  interacted = true;
  const value = input.valueAsNumber;
  if (input.value.trim() === "" || !Number.isFinite(value)) {
    clearResult();
    input.setAttribute("aria-invalid", "true");
    message("Enter a finite Celsius number before converting.", true);
    input.focus();
    return;
  }
  busy = true;
  setControls();
  clearResult();
  input.removeAttribute("aria-invalid");
  message("Converting…");
  try {
    const result = await app.callServerTool({
      name: "celsius_to_fahrenheit",
      arguments: { celsius: value },
    });
    const data = showResult(result);
    // Context sharing is best-effort; a failed context update must not erase a
    // successful conversion or claim that the calculation itself failed.
    try {
      await app.updateModelContext({ structuredContent: data });
    } catch {
      message("Converted. This host could not share the result with the conversation.");
    }
  } catch (error) {
    clearResult();
    message(error instanceof Error ? error.message : "Conversion failed. Please try again.", true);
  } finally {
    busy = false;
    setControls();
  }
}

input.addEventListener("input", () => {
  interacted = true;
  input.removeAttribute("aria-invalid");
  clearResult();
  message("Ready to convert.");
});
form.addEventListener("submit", (event) => {
  event.preventDefault();
  void convert();
});
for (const preset of document.querySelectorAll("[data-celsius]")) {
  preset.addEventListener("click", () => {
    if (!connected || busy) return;
    input.value = preset.dataset.celsius;
    void convert();
  });
}

try {
  const { App } = await import("https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@2.0.0/dist/src/app-with-deps.js");
  app = new App({ name: "Celsius to Fahrenheit", version: "1.0.0" });
  // Hosts can deliver the opening tool input/result immediately on connection.
  // Never let a late opening notification overwrite a user's newer edit.
  app.ontoolinput = ({ arguments: args }) => {
    if (!interacted && Number.isFinite(args?.celsius)) input.value = String(args.celsius);
  };
  app.ontoolresult = (result) => {
    if (interacted) return;
    try { showResult(result); }
    catch (error) { clearResult(); message(error.message, true); }
  };
  app.onhostcontextchanged = applyTheme;
  await app.connect();
  connected = true;
  applyTheme(app.getHostContext());
  setControls();
  if (status.textContent === "Connecting to the app host…") message("Ready to convert.");
} catch {
  message("Could not connect to the app host. Reopen the app to try again, or use the tool’s text result.", true);
  setControls();
}
