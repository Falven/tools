from __future__ import annotations
# ruff: noqa: I001

import ipaddress
import json
import os
import re
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
)

from mcp.server.apps import Apps, ResourceCsp


apps = Apps()
__all__ = ["browser_workflow"]

RESOURCE_URI = "ui://browser-workflow/recorder.html"
ASSETS = Path(__file__).parent
HTML = (ASSETS / "app.html").read_text(encoding="utf-8").replace(
    "<!-- app.js -->",
    f'<script type="module">\n{(ASSETS / "app.js").read_text(encoding="utf-8")}\n</script>',
)

_DATA_DIR = Path(
    os.environ.get("TOOLFORGE_DATA_DIR", str(Path.home() / ".toolforge"))
)
_WORKFLOW_FILE = _DATA_DIR / "browser_workflows.json"
_STORE_LOCK = threading.RLock()
_SESSIONS_LOCK = threading.RLock()
_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSION_TTL_SECONDS = 60 * 60
_MAX_RESPONSE_BYTES = 2_000_000
_MAX_PAGE_TEXT = 24_000
_PARAMETER = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]{0,63})\}\}")
_IGNORED_TAGS = {"script", "style", "noscript", "svg", "template"}
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _Node:
    def __init__(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]] | None = None,
        parent: _Node | None = None,
    ) -> None:
        self.tag = tag
        self.attrs = {key.lower(): value or "" for key, value in (attrs or [])}
        self.parent = parent
        self.children: list[_Node | str] = []

    def get(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)

    def has(self, name: str) -> bool:
        return name in self.attrs


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("[document]")
        self.stack = [self.root]

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        normalized = tag.lower()
        node = _Node(normalized, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if normalized not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == normalized:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].children.append(data)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class _HttpSession:
    def __init__(self) -> None:
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies), _NoRedirect())

    def close(self) -> None:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_workflows() -> dict[str, dict[str, Any]]:
    with _STORE_LOCK:
        if not _WORKFLOW_FILE.exists():
            return {}
        try:
            value = json.loads(_WORKFLOW_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not read the workflow store: {exc}") from exc
        if not isinstance(value, dict):
            raise TypeError("The workflow store is not a JSON object.")
        return value


def _save_workflows(workflows: dict[str, dict[str, Any]]) -> None:
    with _STORE_LOCK:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        temporary = _WORKFLOW_FILE.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(workflows, indent=2, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(_WORKFLOW_FILE)


def _workflow_summary(name: str, workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": workflow.get("description", ""),
        "start_url": workflow.get("start_url", ""),
        "parameters": workflow.get("parameters", []),
        "step_count": len(workflow.get("steps", [])),
        "created_at": workflow.get("created_at"),
        "updated_at": workflow.get("updated_at"),
    }


def _validate_public_url(raw_url: str) -> str:
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise TypeError("A non-empty URL string is required.")
    url = raw_url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// and https:// URLs are supported.")
    if not parsed.hostname:
        raise ValueError("The URL must include a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in URLs are not allowed.")
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve hostname {parsed.hostname!r}.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError(
                "Private, loopback, link-local, reserved, and metadata-network "
                "addresses are blocked."
            )
    return url


def _request(
    client: _HttpSession,
    method: str,
    url: str,
    data: dict[str, str] | None = None,
) -> dict[str, Any]:
    current_url = _validate_public_url(url)
    current_method = method.upper()
    current_data = data
    if current_method not in {"GET", "POST"}:
        raise ValueError("Only GET and POST form workflows are supported.")

    for _ in range(6):
        request_url = current_url
        body: bytes | None = None
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ToolForgeWorkflowRecorder/1.0)"
        }
        if current_method == "GET" and current_data:
            separator = "&" if urlparse(request_url).query else "?"
            request_url += separator + urlencode(current_data)
        elif current_method == "POST":
            body = urlencode(current_data or {}).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        request = Request(
            request_url, data=body, headers=headers, method=current_method
        )
        try:
            response = client.opener.open(request, timeout=20)
        except HTTPError as exc:
            response = exc
        except URLError as exc:
            raise RuntimeError(f"Website request failed: {exc.reason}") from exc

        with response:
            status = response.getcode()
            if status in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise RuntimeError("The website returned a redirect without a URL.")
                current_url = _validate_public_url(urljoin(current_url, location))
                if status == 303 or (
                    status in {301, 302} and current_method == "POST"
                ):
                    current_method = "GET"
                    current_data = None
                continue

            declared_length = response.headers.get("content-length")
            if (
                declared_length
                and declared_length.isdigit()
                and int(declared_length) > _MAX_RESPONSE_BYTES
            ):
                raise ValueError("The page is larger than the 2 MB safety limit.")

            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(65_536)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_RESPONSE_BYTES:
                    raise ValueError("The page is larger than the 2 MB safety limit.")
                chunks.append(chunk)

            content_type = response.headers.get("content-type", "").lower()
            if content_type and not any(
                value in content_type
                for value in ("text/html", "application/xhtml+xml", "text/plain")
            ):
                raise ValueError(
                    f"Unsupported response content type: {content_type.split(';')[0]}."
                )
            encoding = response.headers.get_content_charset() or "utf-8"
            text = b"".join(chunks).decode(encoding, errors="replace")
            return {
                "url": str(response.geturl()),
                "status": status,
                "html": text,
            }
    raise RuntimeError("The website redirected too many times.")


def _parse_html(value: str) -> _Node:
    parser = _DocumentParser()
    parser.feed(value)
    parser.close()
    return parser.root


def _iter_nodes(node: _Node, tags: set[str] | None = None):
    for child in node.children:
        if not isinstance(child, _Node) or child.tag in _IGNORED_TAGS:
            continue
        if tags is None or child.tag in tags:
            yield child
        yield from _iter_nodes(child, tags)


def _selector(element: _Node) -> str:
    indexes: list[str] = []
    current = element
    while current.parent is not None:
        siblings = [
            child for child in current.parent.children if isinstance(child, _Node)
        ]
        indexes.append(str(siblings.index(current)))
        current = current.parent
    return "node:" + "/".join(reversed(indexes))


def _select_node(root: _Node, selector: str) -> _Node | None:
    if not selector.startswith("node:"):
        return None
    current = root
    path = selector[5:]
    if not path:
        return current
    try:
        for raw_index in path.split("/"):
            children = [
                child for child in current.children if isinstance(child, _Node)
            ]
            current = children[int(raw_index)]
    except (ValueError, IndexError):
        return None
    return current


def _text_parts(node: _Node):
    for child in node.children:
        if isinstance(child, str):
            yield child
        elif child.tag not in _IGNORED_TAGS:
            yield from _text_parts(child)


def _clean_text(element: _Node, limit: int = 500) -> str:
    return " ".join(" ".join(_text_parts(element)).split())[:limit]


def _ancestor(field: _Node, tag: str) -> _Node | None:
    current = field.parent
    while current is not None:
        if current.tag == tag:
            return current
        current = current.parent
    return None


def _field_label(field: _Node) -> str:
    field_id = field.get("id")
    root = _ancestor(field, "form") or field.parent
    if field_id and root is not None:
        for label in _iter_nodes(root, {"label"}):
            if label.get("for") != field_id:
                continue
            text = _clean_text(label, 160)
            if text:
                return text
    parent_label = _ancestor(field, "label")
    if parent_label is not None:
        text = _clean_text(parent_label, 160)
        if text:
            return text
    return str(
        field.get("placeholder")
        or field.get("aria-label")
        or field.get("name")
        or field.tag
    )[:160]


def _field_value(field: _Node) -> str:
    if field.tag == "textarea":
        return _clean_text(field, 20_000)
    if field.tag == "select":
        options = list(_iter_nodes(field, {"option"}))
        selected = next((option for option in options if option.has("selected")), None)
        selected = selected or (options[0] if options else None)
        if selected is not None:
            return selected.get("value", _clean_text(selected, 20_000))
        return ""
    return field.get("value")


def _page_view(page: dict[str, Any]) -> dict[str, Any]:
    root = _parse_html(page["html"])
    title_node = next(_iter_nodes(root, {"title"}), None)
    title = _clean_text(title_node, 300) if title_node else ""

    links: list[dict[str, Any]] = []
    for link in list(_iter_nodes(root, {"a"}))[:120]:
        if not link.has("href"):
            continue
        label = _clean_text(link, 220) or str(link.get("aria-label", "Untitled link"))
        href = urljoin(page["url"], link.get("href"))
        if urlparse(href).scheme in {"http", "https"}:
            links.append(
                {
                    "label": label,
                    "url": href,
                    "selector": _selector(link),
                }
            )

    forms: list[dict[str, Any]] = []
    for form in list(_iter_nodes(root, {"form"}))[:30]:
        fields: list[dict[str, Any]] = []
        for field in _iter_nodes(form, {"input", "textarea", "select"}):
            field_type = (
                str(field.get("type", "text")).lower()
                if field.tag == "input"
                else field.tag
            )
            name = field.get("name")
            if (
                not name
                or field_type
                in {"hidden", "submit", "button", "reset", "image", "file"}
            ):
                continue
            options = []
            if field.tag == "select":
                options = [
                    {
                        "value": option.get("value", _clean_text(option, 20_000)),
                        "label": _clean_text(option, 160),
                    }
                    for option in _iter_nodes(field, {"option"})
                ][:100]
            fields.append(
                {
                    "name": str(name),
                    "label": _field_label(field),
                    "type": field_type,
                    "value": _field_value(field) if field_type != "password" else "",
                    "required": field.has("required"),
                    "options": options,
                }
            )
        submit_labels = [
            _clean_text(button, 120)
            or button.get("value", "Submit")
            for button in _iter_nodes(form, {"button", "input"})
            if button.tag == "button"
            or str(button.get("type", "")).lower() in {"submit", "image"}
        ]
        forms.append(
            {
                "selector": _selector(form),
                "method": str(form.get("method", "get")).upper(),
                "action": urljoin(page["url"], form.get("action") or page["url"]),
                "fields": fields,
                "submit_label": submit_labels[0] if submit_labels else "Submit form",
            }
        )

    elements: list[dict[str, str]] = []
    content_tags = {"h1", "h2", "h3", "p", "article", "main", "td", "th", "li"}
    for element in _iter_nodes(root):
        if element.tag not in content_tags and element.get("role") not in {
            "status",
            "alert",
        }:
            continue
        text = _clean_text(element, 500)
        if len(text) >= 2:
            elements.append(
                {
                    "selector": _selector(element),
                    "tag": element.tag,
                    "text": text,
                }
            )
        if len(elements) >= 160:
            break

    page_text = _clean_text(root, _MAX_PAGE_TEXT)
    return {
        "url": page["url"],
        "status": page["status"],
        "title": title,
        "text": page_text,
        "links": links,
        "forms": forms,
        "elements": elements,
    }


def _form_defaults(form: _Node) -> dict[str, str]:
    data: dict[str, str] = {}
    for field in _iter_nodes(form, {"input", "textarea", "select"}):
        name = field.get("name")
        if not name or field.has("disabled"):
            continue
        field_type = str(field.get("type", "text")).lower()
        if field_type in {"submit", "button", "reset", "image", "file"}:
            continue
        if field_type in {"checkbox", "radio"} and not field.has("checked"):
            continue
        data[str(name)] = _field_value(field)
    return data


def _submit_form(
    client: _HttpSession,
    page: dict[str, Any],
    selector: str,
    values: dict[str, str],
) -> dict[str, Any]:
    root = _parse_html(page["html"])
    form = _select_node(root, selector)
    if form is None or form.tag != "form":
        raise ValueError("The recorded form was not found; the website may have changed.")
    data = _form_defaults(form)
    data.update({str(key): str(value) for key, value in values.items()})
    method = str(form.get("method", "get")).upper()
    action = urljoin(page["url"], form.get("action") or page["url"])
    return _request(client, method, action, data)


def _new_client() -> _HttpSession:
    return _HttpSession()


def _cleanup_sessions() -> None:
    cutoff = time.monotonic() - _SESSION_TTL_SECONDS
    expired = [
        session_id
        for session_id, session in _SESSIONS.items()
        if session["touched"] < cutoff
    ]
    for session_id in expired:
        session = _SESSIONS.pop(session_id)
        session["client"].close()


def _get_session(session_id: str) -> dict[str, Any]:
    with _SESSIONS_LOCK:
        _cleanup_sessions()
        session = _SESSIONS.get(session_id)
        if session is None:
            raise ValueError("Recorder session expired. Start the demonstration again.")
        session["touched"] = time.monotonic()
        return session


def _session_result(session_id: str, session: dict[str, Any]) -> dict[str, Any]:
    public_steps = [
        {key: value for key, value in step.items() if key != "_actual_values"}
        for step in session["steps"]
    ]
    return {
        "ok": True,
        "session_id": session_id,
        "page": _page_view(session["page"]),
        "steps": public_steps,
    }


def _substitute(value: str, parameters: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in parameters:
            raise ValueError(f"Missing required workflow parameter: {name}")
        return str(parameters[name])

    return _PARAMETER.sub(replace, value)


def _run_workflow(
    workflow_name: str, parameters: dict[str, str] | None
) -> dict[str, Any]:
    workflows = _load_workflows()
    workflow = workflows.get(workflow_name)
    if workflow is None:
        raise ValueError(f"Unknown workflow: {workflow_name}")
    supplied = {str(key): str(value) for key, value in (parameters or {}).items()}
    required = workflow.get("parameters", [])
    missing = [name for name in required if name not in supplied]
    if missing:
        raise ValueError("Missing required parameters: " + ", ".join(missing))

    client = _new_client()
    extracted: dict[str, str] = {}
    trace: list[dict[str, Any]] = []
    try:
        page = _request(client, "GET", _substitute(workflow["start_url"], supplied))
        trace.append({"step": 0, "type": "start", "url": page["url"], "status": page["status"]})
        for index, step in enumerate(workflow.get("steps", []), start=1):
            step_type = step.get("type")
            if step_type == "navigate":
                page = _request(
                    client, "GET", _substitute(str(step["url"]), supplied)
                )
                trace.append(
                    {
                        "step": index,
                        "type": "navigate",
                        "url": page["url"],
                        "status": page["status"],
                    }
                )
            elif step_type == "submit":
                values = {
                    str(key): _substitute(str(value), supplied)
                    for key, value in step.get("values", {}).items()
                }
                page = _submit_form(client, page, str(step["selector"]), values)
                trace.append(
                    {
                        "step": index,
                        "type": "submit",
                        "url": page["url"],
                        "status": page["status"],
                    }
                )
            elif step_type == "extract":
                root = _parse_html(page["html"])
                element = _select_node(root, str(step["selector"]))
                if element is None:
                    raise ValueError(
                        f"Extraction {step.get('name')!r} failed at step {index}; "
                        "the website may have changed."
                    )
                extracted[str(step["name"])] = _clean_text(element, 10_000)
                trace.append(
                    {
                        "step": index,
                        "type": "extract",
                        "name": step["name"],
                    }
                )
            else:
                raise ValueError(f"Unsupported recorded step type: {step_type!r}")

        view = _page_view(page)
        return {
            "ok": True,
            "workflow": workflow_name,
            "final_url": view["url"],
            "status": view["status"],
            "title": view["title"],
            "extracted": extracted,
            "page_text": view["text"],
            "trace": trace,
        }
    except Exception as exc:
        raise RuntimeError(f"Workflow failed: {exc}") from exc
    finally:
        client.close()


@apps.tool(resource_uri=RESOURCE_URI)
def browser_workflow(
    action: Literal["studio", "run", "list", "inspect", "delete"] = "studio",
    workflow: str | None = None,
    parameters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record and replay parameterized browser-like workflows for public websites.

    Use action="studio" to open the interactive recorder. The user demonstrates a
    workflow by navigating links and submitting HTML forms in a safe proxied page
    viewer, marks changing values as {{parameters}}, selects page elements to
    extract, and saves the workflow. Use action="run" with a saved workflow name
    and its parameter values to replay it in a fresh cookie session. "list"
    returns saved workflow metadata, "inspect" returns one definition, and
    "delete" removes one.

    This tool supports server-rendered public HTTP(S) pages and GET/POST forms; it
    does not execute JavaScript, solve CAPTCHAs, upload files, access private
    networks, or reuse the user's normal browser login. Saved workflows persist
    on the ToolForge server. Do not save passwords, session tokens, or other
    secrets as literal field values—mark them as parameters instead.
    """
    try:
        if action == "studio":
            workflows = _load_workflows()
            return {
                "ok": True,
                "mode": "studio",
                "message": (
                    "Open the Browser Workflow Studio to demonstrate and save a "
                    "workflow. Non-App clients can use list, inspect, run, and delete."
                ),
                "workflows": [
                    _workflow_summary(name, value)
                    for name, value in sorted(workflows.items())
                ],
                "limitations": [
                    "No JavaScript execution",
                    "Public HTTP(S) pages only",
                    "GET and POST HTML forms only",
                    "Fresh cookie session for every replay",
                ],
            }
        if action == "list":
            workflows = _load_workflows()
            return {
                "ok": True,
                "workflows": [
                    _workflow_summary(name, value)
                    for name, value in sorted(workflows.items())
                ],
            }
        if action == "run":
            if not workflow:
                raise ValueError("workflow is required for action='run'.")
            return _run_workflow(workflow, parameters)
        if action == "inspect":
            if not workflow:
                raise ValueError("workflow is required for action='inspect'.")
            value = _load_workflows().get(workflow)
            if value is None:
                raise ValueError(f"Unknown workflow: {workflow}")
            return {"ok": True, "name": workflow, "workflow": value}
        if action == "delete":
            if not workflow:
                raise ValueError("workflow is required for action='delete'.")
            workflows = _load_workflows()
            if workflow not in workflows:
                raise ValueError(f"Unknown workflow: {workflow}")
            del workflows[workflow]
            _save_workflows(workflows)
            return {"ok": True, "deleted": workflow}
        raise ValueError(f"Unsupported action: {action}")
    except Exception as exc:  # noqa: BLE001 - return a stable MCP error envelope.
        return {"ok": False, "error": str(exc)}


@apps.tool(
    resource_uri=RESOURCE_URI,
    visibility=["app"],
    name="browser_workflow_app_action",
)
def _browser_workflow_app_action(
    operation: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = payload or {}
    try:
        if operation == "start":
            url = _validate_public_url(str(data.get("url", "")))
            client = _new_client()
            try:
                page = _request(client, "GET", url)
            except Exception:
                client.close()
                raise
            session_id = uuid.uuid4().hex
            session = {
                "client": client,
                "start_url": page["url"],
                "page": page,
                "steps": [],
                "touched": time.monotonic(),
            }
            with _SESSIONS_LOCK:
                _cleanup_sessions()
                _SESSIONS[session_id] = session
            return _session_result(session_id, session)

        if operation == "navigate":
            session_id = str(data.get("session_id", ""))
            session = _get_session(session_id)
            url = _validate_public_url(str(data.get("url", "")))
            page = _request(session["client"], "GET", url)
            session["page"] = page
            session["steps"].append(
                {
                    "type": "navigate",
                    "url": url,
                    "label": str(data.get("label", ""))[:300],
                }
            )
            return _session_result(session_id, session)

        if operation == "submit":
            session_id = str(data.get("session_id", ""))
            session = _get_session(session_id)
            selector = str(data.get("selector", ""))
            actual_values = {
                str(key): str(value)
                for key, value in dict(data.get("actual_values") or {}).items()
            }
            recorded_values = {
                str(key): str(value)
                for key, value in dict(data.get("recorded_values") or {}).items()
            }
            page = _submit_form(
                session["client"], session["page"], selector, actual_values
            )
            session["page"] = page
            session["steps"].append(
                {
                    "type": "submit",
                    "selector": selector,
                    "values": recorded_values,
                    "_actual_values": actual_values,
                }
            )
            return _session_result(session_id, session)

        if operation == "extract":
            session_id = str(data.get("session_id", ""))
            session = _get_session(session_id)
            name = str(data.get("name", "")).strip()
            selector = str(data.get("selector", "")).strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
                raise ValueError(
                    "Extraction name must be a letter/underscore followed by "
                    "letters, numbers, or underscores."
                )
            session["steps"].append(
                {"type": "extract", "name": name, "selector": selector}
            )
            return _session_result(session_id, session)

        if operation == "undo":
            session_id = str(data.get("session_id", ""))
            session = _get_session(session_id)
            if not session["steps"]:
                return _session_result(session_id, session)
            retained = session["steps"][:-1]
            client = _new_client()
            try:
                page = _request(client, "GET", session["start_url"])
                for step in retained:
                    if step["type"] == "navigate":
                        page = _request(client, "GET", step["url"])
                    elif step["type"] == "submit":
                        page = _submit_form(
                            client,
                            page,
                            step["selector"],
                            step.get("_actual_values", step.get("values", {})),
                        )
            except Exception:
                client.close()
                raise
            session["client"].close()
            session["client"] = client
            session["page"] = page
            session["steps"] = retained
            return _session_result(session_id, session)

        if operation == "save":
            session_id = str(data.get("session_id", ""))
            session = _get_session(session_id)
            name = str(data.get("name", "")).strip()
            description = str(data.get("description", "")).strip()[:1000]
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", name):
                raise ValueError(
                    "Workflow name must be lowercase snake_case, start with a "
                    "letter, and be at most 48 characters."
                )
            parameters_found = sorted(
                {
                    match.group(1)
                    for step in session["steps"]
                    for value in (
                        [step.get("url", "")]
                        if step.get("type") == "navigate"
                        else list(step.get("values", {}).values())
                    )
                    for match in _PARAMETER.finditer(str(value))
                }
                | {
                    match.group(1)
                    for match in _PARAMETER.finditer(session["start_url"])
                }
            )
            workflows = _load_workflows()
            previous = workflows.get(name, {})
            timestamp = _utc_now()
            saved_steps = [
                {key: value for key, value in step.items() if key != "_actual_values"}
                for step in session["steps"]
            ]
            workflows[name] = {
                "version": 1,
                "description": description,
                "start_url": session["start_url"],
                "parameters": parameters_found,
                "steps": saved_steps,
                "created_at": previous.get("created_at", timestamp),
                "updated_at": timestamp,
            }
            if len(workflows) > 100:
                raise ValueError("The workflow store is limited to 100 workflows.")
            _save_workflows(workflows)
            return {
                "ok": True,
                "saved": _workflow_summary(name, workflows[name]),
                "workflows": [
                    _workflow_summary(key, value)
                    for key, value in sorted(workflows.items())
                ],
            }

        if operation == "list":
            workflows = _load_workflows()
            return {
                "ok": True,
                "workflows": [
                    _workflow_summary(name, value)
                    for name, value in sorted(workflows.items())
                ],
            }

        raise ValueError(f"Unsupported App operation: {operation}")
    except Exception as exc:  # noqa: BLE001 - return a stable App error envelope.
        return {"ok": False, "error": str(exc)}


apps.add_html_resource(
    RESOURCE_URI,
    HTML,
    title="Browser Workflow Studio",
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
)
