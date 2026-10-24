import { App } from '@modelcontextprotocol/ext-apps';

const app = new App({ name: 'Contoso request', version: '1.0.0' });
const form = document.getElementById('request-form');
const objective = document.getElementById('business-objective');
const save = document.getElementById('save');
const reload = document.getElementById('reload');
const message = document.getElementById('message');
let requestId = '';
let request = null;
let connected = false;
let busy = false;

function status(text, error = false) {
  message.textContent = text;
  message.dataset.error = String(error);
}

function availability(working) {
  busy = working;
  form.setAttribute('aria-busy', String(working));
  save.disabled = working || !request || request.status !== 'draft';
  objective.disabled = working || !request || request.status !== 'draft';
  reload.disabled = working || !connected || !requestId;
}

function unpack(result) {
  if (result.isError) {
    const text = result.content?.filter(item => item.type === 'text').map(item => item.text).join(' ');
    throw new Error(text || 'The request could not be completed.');
  }
  const data = result.structuredContent;
  if (!data || !['request_id', 'title', 'business_objective', 'status', 'next_action', 'revision'].every(key => typeof data[key] === 'string')) {
    throw new Error('The saved request response is incomplete.');
  }
  return data;
}

function show(data) {
  request = data;
  document.getElementById('request-title').textContent = data.title;
  document.getElementById('request-id').textContent = data.request_id;
  document.getElementById('request-status').textContent = '· ' + data.status;
  document.getElementById('next-action').textContent = data.next_action;
  objective.value = data.business_objective;
}

async function load() {
  if (busy || !connected || !requestId) return;
  availability(true);
  status('Loading the saved request…');
  try {
    show(unpack(await app.callServerTool({
      name: 'contoso_open_request',
      arguments: { request_id: requestId },
    })));
    status('Latest saved request loaded.');
  } catch (error) {
    request = null;
    status(error.message, true);
  } finally {
    availability(false);
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !request || request.status !== 'draft') return;
  const arguments_ = {
    request_id: request.request_id,
    business_objective: objective.value,
    revision: request.revision,
  };
  availability(true);
  status('Saving draft…');
  try {
    show(unpack(await app.callServerTool({
      name: 'contoso_save_request',
      arguments: arguments_,
    })));
    status('Draft saved.');
  } catch (error) {
    request = null;
    status(error.message + ' Reload the saved request before trying again.', true);
  } finally {
    availability(false);
  }
});

reload.addEventListener('click', load);

app.ontoolresult = result => {
  if (requestId) return;
  try {
    // Retained result data is not current authority; use only its ID for a fresh read.
    requestId = unpack(result).request_id;
    if (connected) void load();
  } catch (error) {
    status(error.message, true);
  }
};

if (window.parent === window) {
  status('Open this form from a Contoso request in your agent.', true);
} else {
  app.connect().then(() => {
    connected = true;
    availability(false);
    if (requestId) void load();
  }).catch(error => status('Could not connect to the agent. Reopen the form. ' + error.message, true));
}
