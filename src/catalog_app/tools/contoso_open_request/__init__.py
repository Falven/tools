"""Open a saved Contoso request and edit its draft business objective."""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from azure.core.exceptions import (
    AzureError,
    ResourceModifiedError,
    ResourceNotFoundError,
)
from azure.data.tables import TableClient
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    TypeAdapter,
    ValidationError,
    model_validator,
)

RESOURCE_URI = "ui://contoso-request/app.html"
RequestId = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9_-]{1,128}$")]
AnswerText = Annotated[str, Field(strict=True, max_length=4000)]
QuestionSetRevision = Annotated[str, Field(strict=True, min_length=1, max_length=128)]
Revision = Annotated[
    str, Field(strict=True, max_length=256, pattern=r'^(?:W/)?"[^"\r\n]+"$')
]


class Question(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: RequestId
    type: Literal["text", "choice", "yes_no"]
    prompt: Annotated[str, Field(min_length=1, max_length=4000)]
    required: bool
    choices: list[AnswerText] | None = None

    @model_validator(mode="after")
    def valid_choices(self):
        if not self.prompt.strip():
            raise ValueError("A question needs a prompt.")
        if self.type == "choice":
            if (
                not self.choices
                or any(not value.strip() for value in self.choices)
                or len(set(self.choices)) != len(self.choices)
            ):
                raise ValueError("Choice questions need distinct, nonempty choices.")
        elif self.choices is not None:
            raise ValueError("Only choice questions may define choices.")
        return self


def _validate_answers(questions: list[Question], answers):
    by_id = {question.id: question for question in questions}
    for question_id, answer in answers.items():
        question = by_id.get(question_id)
        if question is None:
            raise ToolError("An answer refers to an unknown clarification question.")
        if answer is None:
            continue
        valid = (
            isinstance(answer, bool)
            if question.type == "yes_no"
            else isinstance(answer, str)
        )
        if question.type == "choice":
            valid = valid and answer in question.choices
        if not valid:
            raise ToolError(
                f"The answer for {question_id} has the wrong type or choice."
            )


def _clarification(entity, expected_revision: str | None = None):
    if "Questions" not in entity and entity["Status"] != "needs_clarification":
        return [], {}, None
    try:
        revision = TypeAdapter(QuestionSetRevision).validate_python(
            entity["QuestionSetRevision"]
        )
        questions = TypeAdapter(list[Question]).validate_json(entity["Questions"])
        answers = TypeAdapter(dict[str, AnswerText | StrictBool]).validate_json(
            entity["Answers"]
        )
        if (
            not revision.strip()
            or not questions
            or len({question.id for question in questions}) != len(questions)
        ):
            raise ValueError("Invalid clarification questions.")
        _validate_answers(questions, answers)
    except (KeyError, TypeError, ValueError, ValidationError, ToolError):
        raise ToolError("The saved clarification is incomplete or invalid.") from None
    if expected_revision is not None and revision != expected_revision:
        raise ToolError(
            "The clarification questions changed. Reopen the request before saving."
        )
    return questions, answers, revision


def _missing_answers(questions: list[Question], answers) -> list[str]:
    return [
        question.id
        for question in questions
        if question.required
        and (
            question.id not in answers
            or isinstance(answers[question.id], str)
            and not answers[question.id].strip()
        )
    ]


def _customer_partition() -> str:
    caller = get_access_token()
    claims = (caller.claims or {}) if caller else {}
    if (
        claims.get("idtyp") == "app"
        or not isinstance(claims.get("scp"), str)
        or not claims["scp"].strip()
    ):
        raise ToolError("Sign in with a delegated customer account.")
    try:
        tenant, customer = UUID(claims["tid"]), UUID(claims["oid"])
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ToolError("The signed-in customer identity is unavailable.") from None
    return f"contoso:{tenant}:{customer}"


@contextmanager
def _storage():
    connection = os.environ.get("CONTOSO_STORAGE_CONNECTION_STRING", "")
    table_name = os.environ.get("CONTOSO_REQUESTS_TABLE", "")
    if not connection.strip() or not table_name.strip():
        raise ToolError(
            "Set CONTOSO_STORAGE_CONNECTION_STRING and CONTOSO_REQUESTS_TABLE in ToolForge."
        )
    try:
        with TableClient.from_connection_string(
            connection, table_name=table_name
        ) as table:
            yield table
    except ResourceNotFoundError:
        raise ToolError("Request not found.") from None
    except ResourceModifiedError:
        raise ToolError("This request changed. Reopen it before saving.") from None
    except (AzureError, ValueError):
        # Azure errors can include configured URLs or credentials; keep them out of Tool output.
        raise ToolError(
            "Contoso storage is unavailable. Check its access and configuration."
        ) from None


def _owned_request(table: TableClient, partition: str, request_id: str):
    entity = table.get_entity(partition_key=partition, row_key=request_id)
    if entity.get("DemoId") != "contoso-demo":
        raise ToolError("Request not found.")
    _validate_request(entity)
    return entity


def _validate_request(entity):
    if any(
        not isinstance(entity.get(key), str)
        for key in ("Title", "BusinessObjective", "Status")
    ):
        raise ToolError("The saved Contoso request is incomplete.")
    if any(
        key in entity and not isinstance(entity[key], str)
        for key in (
            "Capabilities",
            "SystemsAndConstraints",
            "DecisionMaker",
            "PreferredDeadline",
        )
    ):
        raise ToolError("The saved Contoso brief is invalid.")


def _next_action(status: str) -> str:
    return {
        "draft": "Review your business objective and save any changes.",
        "needs_clarification": "Answer Contoso's questions and submit your clarification.",
        "submitted": "Your request has been submitted to Contoso.",
        "in_review": "Contoso is reviewing your request.",
    }.get(status, "This request is read-only.")


def _view(entity, revision: str) -> dict[str, Any]:
    questions, answers, question_revision = _clarification(entity)
    return {
        "request_id": entity["RowKey"],
        "title": entity["Title"],
        "business_objective": entity["BusinessObjective"],
        "status": entity["Status"],
        "next_action": _next_action(entity["Status"]),
        "revision": revision,
        "view": {"draft": "intake", "needs_clarification": "clarification"}.get(
            entity["Status"], "status"
        ),
        "brief": {
            "requested_software": entity["Title"],
            "business_objective": entity["BusinessObjective"],
            "capabilities": entity.get("Capabilities", ""),
            "systems_and_constraints": entity.get("SystemsAndConstraints", ""),
            "decision_maker": entity.get("DecisionMaker", ""),
            "preferred_deadline": entity.get("PreferredDeadline", ""),
        },
        "questions": [question.model_dump(exclude_none=True) for question in questions],
        "answers": answers,
        "question_set_revision": question_revision,
        "missing_required_answers": _missing_answers(questions, answers),
    }


def contoso_open_request(request_id: RequestId) -> dict[str, Any]:
    """Open the signed-in customer's saved software request without changing it."""
    partition = _customer_partition()
    with _storage() as table:
        entity = _owned_request(table, partition, request_id)
        return _view(entity, entity.metadata["etag"])


def contoso_request_app() -> str:
    """Serve the request form without reading customer records."""
    assets = Path(__file__).parent
    html = (assets / "app.html").read_text(encoding="utf-8")
    script = (assets / "app.js").read_text(encoding="utf-8")
    if html.count("<!-- app.js -->") != 1:
        raise ToolError("The Contoso request interface is incomplete.")
    return html.replace(
        "<!-- app.js -->", f'<script type="module">\n{script}\n</script>'
    )


def register(server: MCPServer) -> None:
    server.add_tool(
        contoso_open_request,
        title="Open Contoso request",
        meta={"ui": {"resourceUri": RESOURCE_URI}},
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    server.resource(
        RESOURCE_URI,
        mime_type="text/html;profile=mcp-app",
        title="Contoso request",
        meta={"ui": {"csp": {"resourceDomains": [], "connectDomains": []}}},
    )(contoso_request_app)
