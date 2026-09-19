import { App } from "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@2.0.0/dist/src/app-with-deps.js";

const $ = (selector) => document.querySelector(selector);
const app = new App({ name: "Browser Workflow Studio", version: "1.0.0" });
let sessionId = null;
let currentPage = null;
let steps = [];
let workflows = [];
let selectedWorkflow = null;

const status = (message, kind = "") => {
  const node = $("#status");
  node.textContent = message;
  node.className = kind;
};

const setBusy = (busy) => {
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = busy;
  });
};

const callApp = async (operation, payload = {}) => {
  const result = await app.callServerTool({
    name: "browser_workflow_app_action",
    arguments: { operation, payload },
  });
  const data = result.structuredContent || {};
  if (result.isError || !data.ok) {
    throw new Error(data.error || JSON.stringify(result.content));
  }
  return data;
};

const safeName = (value, fallback = "value") => {
  const cleaned = String(value || fallback)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^[^a-z_]+/, "")
    .slice(0, 64);
  return cleaned || fallback;
};

const renderWorkflows = () => {
  const root = $("#workflow-list");
  root.replaceChildren();
  if (!workflows.length) {
    const empty = document.createElement("span");
    empty.className = "muted";
    empty.textContent = "No saved workflows yet.";
    root.append(empty);
    return;
  }
  workflows.forEach((workflow) => {
    const button = document.createElement("button");
    button.className = "workflow";
    button.type = "button";
    const name = document.createElement("strong");
    name.textContent = workflow.name;
    const meta = document.createElement("span");
    meta.textContent = `${workflow.step_count} steps · ${workflow.parameters.length} parameters`;
    button.append(name, meta);
    button.addEventListener("click", () => showRunner(workflow));
    root.append(button);
  });
};

const showRunner = (workflow) => {
  selectedWorkflow = workflow;
  $("#runner").hidden = false;
  $("#runner-title").textContent = `Run ${workflow.name}`;
  $("#runner-description").textContent =
    workflow.description || `Starts at ${workflow.start_url}`;
  const root = $("#runner-parameters");
  root.replaceChildren();
  workflow.parameters.forEach((parameter) => {
    const wrapper = document.createElement("label");
    wrapper.textContent = parameter;
    const input = document.createElement("input");
    input.dataset.parameter = parameter;
    input.placeholder = `Value for ${parameter}`;
    wrapper.append(input);
    root.append(wrapper);
  });
  $("#run-result").hidden = true;
  $("#runner").scrollIntoView({ behavior: "smooth", block: "start" });
};

const stepText = (step) => {
  if (step.type === "navigate") return `Navigate: ${step.label || step.url}`;
  if (step.type === "submit") {
    const fields = Object.keys(step.values || {});
    return `Submit form${fields.length ? ` (${fields.join(", ")})` : ""}`;
  }
  if (step.type === "extract") return `Extract ${step.name}`;
  return step.type;
};

const renderSteps = () => {
  const root = $("#steps");
  root.replaceChildren();
  steps.forEach((step) => {
    const item = document.createElement("li");
    item.textContent = stepText(step);
    root.append(item);
  });
  $("#step-count").textContent = String(steps.length);
};

const renderLinks = (links) => {
  const root = $("#links");
  root.replaceChildren();
  if (!links.length) {
    root.textContent = "No HTTP(S) links found.";
    root.className = "list muted";
    return;
  }
  links.slice(0, 80).forEach((link) => {
    const button = document.createElement("button");
    button.className = "workflow";
    button.type = "button";
    const label = document.createElement("strong");
    label.textContent = link.label;
    const url = document.createElement("span");
    url.textContent = link.url;
    button.append(label, url);
    button.addEventListener("click", async () => {
      setBusy(true);
      status(`Opening ${link.label}…`);
      try {
        const data = await callApp("navigate", {
          session_id: sessionId,
          url: link.url,
          label: link.label,
        });
        applySession(data);
        status("Navigation recorded.", "success");
      } catch (error) {
        status(String(error), "error");
      } finally {
        setBusy(false);
      }
    });
    root.append(button);
  });
};

const makeFieldControl = (field) => {
  let control;
  if (field.type === "select") {
    control = document.createElement("select");
    field.options.forEach((option) => {
      const node = document.createElement("option");
      node.value = option.value;
      node.textContent = option.label || option.value;
      node.selected = option.value === field.value;
      control.append(node);
    });
  } else if (field.type === "textarea") {
    control = document.createElement("textarea");
    control.value = field.value || "";
  } else {
    control = document.createElement("input");
    control.type = ["password", "email", "number", "date", "search", "url"].includes(field.type)
      ? field.type
      : "text";
    control.value = field.value || "";
  }
  control.dataset.field = field.name;
  if (field.required) control.required = true;
  return control;
};

const renderForms = (forms) => {
  const root = $("#forms");
  root.replaceChildren();
  if (!forms.length) {
    root.textContent = "No HTML forms found.";
    root.className = "list muted";
    return;
  }
  forms.forEach((form, formIndex) => {
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.selector = form.selector;
    const heading = document.createElement("h3");
    heading.textContent = `${form.method} form → ${form.action}`;
    card.append(heading);
    form.fields.forEach((field) => {
      const grid = document.createElement("div");
      grid.className = "field-grid";
      const label = document.createElement("label");
      label.textContent = field.label;
      const controls = document.createElement("div");
      const input = makeFieldControl(field);
      const parameter = document.createElement("div");
      parameter.className = "parameter";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = field.type === "password";
      checkbox.dataset.parameterize = field.name;
      const parameterName = document.createElement("input");
      parameterName.placeholder = "parameter_name";
      parameterName.value = safeName(field.name);
      parameterName.dataset.parameterName = field.name;
      parameterName.disabled = !checkbox.checked;
      checkbox.addEventListener("change", () => {
        parameterName.disabled = !checkbox.checked;
      });
      const parameterLabel = document.createElement("label");
      parameterLabel.className = "row";
      parameterLabel.append(checkbox, document.createTextNode("Parameterize"));
      parameter.append(parameterLabel, parameterName);
      controls.append(input, parameter);
      grid.append(label, controls);
      card.append(grid);
    });
    const submit = document.createElement("button");
    submit.className = "soft";
    submit.type = "button";
    submit.textContent = `Demonstrate: ${form.submit_label}`;
    submit.style.marginTop = "10px";
    submit.addEventListener("click", async () => {
      const actualValues = {};
      const recordedValues = {};
      card.querySelectorAll("[data-field]").forEach((input) => {
        actualValues[input.dataset.field] = input.value;
        const checkbox = card.querySelector(
          `[data-parameterize="${CSS.escape(input.dataset.field)}"]`,
        );
        const parameterInput = card.querySelector(
          `[data-parameter-name="${CSS.escape(input.dataset.field)}"]`,
        );
        recordedValues[input.dataset.field] = checkbox?.checked
          ? `{{${safeName(parameterInput?.value, safeName(input.dataset.field))}}}`
          : input.value;
      });
      setBusy(true);
      status(`Submitting form ${formIndex + 1}…`);
      try {
        const data = await callApp("submit", {
          session_id: sessionId,
          selector: form.selector,
          actual_values: actualValues,
          recorded_values: recordedValues,
        });
        applySession(data);
        status("Form submission recorded.", "success");
      } catch (error) {
        status(String(error), "error");
      } finally {
        setBusy(false);
      }
    });
    card.append(submit);
    root.append(card);
  });
};

const renderElements = (elements) => {
  const root = $("#elements");
  root.replaceChildren();
  elements.slice(0, 100).forEach((element, index) => {
    const row = document.createElement("div");
    row.className = "element";
    const text = document.createElement("div");
    const tag = document.createElement("span");
    tag.className = "pill";
    tag.textContent = element.tag;
    const content = document.createElement("p");
    content.textContent = element.text;
    text.append(tag, content);
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Extract";
    button.addEventListener("click", async () => {
      const proposed = safeName(
        element.text.split(/\s+/).slice(0, 4).join("_"),
        `output_${index + 1}`,
      );
      const name = window.prompt("Name this returned value:", proposed);
      if (!name) return;
      setBusy(true);
      try {
        const data = await callApp("extract", {
          session_id: sessionId,
          selector: element.selector,
          name: safeName(name, proposed),
        });
        applySession(data);
        status(`Extraction “${safeName(name, proposed)}” recorded.`, "success");
      } catch (error) {
        status(String(error), "error");
      } finally {
        setBusy(false);
      }
    });
    row.append(text, button);
    root.append(row);
  });
};

const applySession = (data) => {
  sessionId = data.session_id;
  currentPage = data.page;
  steps = data.steps || [];
  $("#recorder").hidden = false;
  $("#page-status").textContent = String(currentPage.status);
  $("#page-url").textContent = currentPage.url;
  $("#page-title").textContent = currentPage.title || "Untitled page";
  $("#page-text").textContent = currentPage.text || "";
  renderLinks(currentPage.links || []);
  renderForms(currentPage.forms || []);
  renderElements(currentPage.elements || []);
  renderSteps();
};

$("#start").addEventListener("click", async () => {
  const url = $("#start-url").value.trim();
  if (!url) {
    status("Enter a public HTTP(S) URL.", "error");
    return;
  }
  setBusy(true);
  status("Opening the page through the safe proxy…");
  try {
    const data = await callApp("start", { url });
    applySession(data);
    status("Recorder ready. Use the links and forms below.", "success");
  } catch (error) {
    status(String(error), "error");
  } finally {
    setBusy(false);
  }
});

$("#undo").addEventListener("click", async () => {
  if (!sessionId || !steps.length) return;
  setBusy(true);
  try {
    const data = await callApp("undo", { session_id: sessionId });
    applySession(data);
    status("Last step removed.", "success");
  } catch (error) {
    status(String(error), "error");
  } finally {
    setBusy(false);
  }
});

$("#save").addEventListener("click", async () => {
  if (!sessionId) return;
  setBusy(true);
  try {
    const data = await callApp("save", {
      session_id: sessionId,
      name: $("#workflow-name").value.trim(),
      description: $("#workflow-description").value.trim(),
    });
    workflows = data.workflows || workflows;
    renderWorkflows();
    status(`Saved ${data.saved.name}. It is ready for action="run".`, "success");
  } catch (error) {
    status(String(error), "error");
  } finally {
    setBusy(false);
  }
});

$("#run").addEventListener("click", async () => {
  if (!selectedWorkflow) return;
  const parameters = {};
  document.querySelectorAll("#runner-parameters [data-parameter]").forEach((input) => {
    parameters[input.dataset.parameter] = input.value;
  });
  setBusy(true);
  const output = $("#run-result");
  output.hidden = false;
  output.textContent = "Running…";
  try {
    const result = await app.callServerTool({
      name: "browser_workflow",
      arguments: {
        action: "run",
        workflow: selectedWorkflow.name,
        parameters,
      },
    });
    const data = result.structuredContent || {};
    output.textContent = JSON.stringify(data, null, 2);
    if (!data.ok) throw new Error(data.error || "Workflow failed.");
    await app.updateModelContext({ structuredContent: data });
  } catch (error) {
    output.textContent = String(error);
  } finally {
    setBusy(false);
  }
});

app.ontoolresult = (result) => {
  const data = result.structuredContent || {};
  if (Array.isArray(data.workflows)) {
    workflows = data.workflows;
    renderWorkflows();
  }
};

try {
  await app.connect();
  const data = await callApp("list");
  workflows = data.workflows || [];
  renderWorkflows();
  status("Ready.");
} catch (error) {
  status(`Could not connect to the ToolForge App bridge: ${error}`, "error");
}
