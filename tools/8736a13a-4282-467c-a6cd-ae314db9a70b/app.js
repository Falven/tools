import { App } from "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@2.0.0/dist/src/app-with-deps.js";

const countOutput = document.querySelector("#count");
const buttons = document.querySelectorAll("button");
const app = new App({ name: "Simple Counter", version: "1.1.0" });

async function update(action) {
  buttons.forEach((button) => { button.disabled = true; });
  try {
    const result = await app.callServerTool({
      name: "update_simple_counter",
      arguments: { action },
    });
    if (result.isError) throw new Error(JSON.stringify(result.content));
    countOutput.value = String(result.structuredContent.initial_count);
  } catch (error) {
    countOutput.textContent = String(error);
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

// Fetch current server state instead of replaying the saved conversation result.
app.ontoolresult = () => update("read");
buttons.forEach((button) => {
  button.addEventListener("click", () => update(button.id));
});

try {
  await app.connect();
} catch (error) {
  countOutput.textContent = String(error);
}
