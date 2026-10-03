import { App } from "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@2.0.0/dist/src/app-with-deps.js";

const greeting = document.querySelector("h1");
const app = new App({ name: "Hello World", version: "1.0.0" });

app.ontoolresult = (result) => {
  if (result.isError) return;
  const text = result.content?.find((item) => item.type === "text")?.text;
  if (text) greeting.textContent = text;
};

try {
  await app.connect();
} catch (error) {
  // The static greeting remains visible even without an MCP Apps host.
  console.warn("Hello World: host connection unavailable", error);
}
