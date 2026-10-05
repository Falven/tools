"""Read the saved daily AI briefing without researching or publishing it."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

_SNAPSHOT_PATH = Path(__file__).resolve().with_name("latest.json")
_NEW_YORK = ZoneInfo("America/New_York")


class DailyAIBriefing(TypedDict):
    edition_date: str
    covers_date: str
    timezone: Literal["America/New_York"]
    generated_at: str
    briefing_markdown: str
    source_urls: list[str]
    source_access_limitations: list[str]
    is_current: bool


_SAVED_FIELDS = DailyAIBriefing.__required_keys__ - {"is_current"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _invalid(reason: str) -> ToolError:
    return ToolError(f"Invalid daily AI briefing snapshot (latest.json): {reason}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate field {key!r}")
        result[key] = value
    return result


def _calendar_date(value: object, field: str) -> date:
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        except ValueError:
            pass
    raise _invalid(f"{field} must be a valid date in canonical YYYY-MM-DD form.")


def _valid_source_url(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    try:
        parts = urlsplit(value)
        return (
            parts.scheme in {"http", "https"}
            and bool(parts.hostname)
            and parts.username is None
            and parts.password is None
            and (parts.port is None or parts.port > 0)
        )
    except ValueError:
        return False


def _read_briefing() -> DailyAIBriefing:
    try:
        snapshot = json.loads(
            _SNAPSHOT_PATH.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except FileNotFoundError as exc:
        raise ToolError("Daily AI briefing unavailable: latest.json is missing.") from exc
    except (OSError, UnicodeError) as exc:
        raise ToolError("Daily AI briefing unavailable: latest.json cannot be read as UTF-8.") from exc
    except ValueError as exc:
        raise _invalid(f"malformed JSON: {exc}") from exc

    if not isinstance(snapshot, dict) or set(snapshot) != _SAVED_FIELDS:
        raise _invalid("expected exactly these seven saved fields: " + ", ".join(sorted(_SAVED_FIELDS)))
    if snapshot["timezone"] != "America/New_York":
        raise _invalid("timezone must be America/New_York.")

    edition = _calendar_date(snapshot["edition_date"], "edition_date")
    coverage = _calendar_date(snapshot["covers_date"], "covers_date")
    if (edition - coverage).days != 1:
        raise _invalid("covers_date must be the calendar day immediately before edition_date.")

    value = snapshot["generated_at"]
    try:
        if not isinstance(value, str) or "T" not in value or not value.endswith(("Z", "+00:00")):
            raise ValueError
        generated_at = datetime.fromisoformat(value)
        if generated_at.utcoffset() != timedelta(0):
            raise ValueError
    except ValueError as exc:
        raise _invalid("generated_at must be an ISO 8601 UTC timestamp ending in Z or +00:00.") from exc

    now = _utc_now()
    today = now.astimezone(_NEW_YORK).date()
    if edition > today:
        raise _invalid("edition_date is in the future in America/New_York.")
    if generated_at > now:
        raise _invalid("generated_at is in the future.")

    markdown = snapshot["briefing_markdown"]
    if not isinstance(markdown, str) or not markdown.strip():
        raise _invalid("briefing_markdown must be a nonempty string.")
    urls = snapshot["source_urls"]
    if not isinstance(urls, list) or not urls or not all(_valid_source_url(url) for url in urls):
        raise _invalid("source_urls must be a nonempty array of absolute HTTP(S) URLs without credentials.")
    limitations = snapshot["source_access_limitations"]
    if not isinstance(limitations, list) or not all(
        isinstance(item, str) and item.strip() for item in limitations
    ):
        raise _invalid("source_access_limitations must be an array of nonempty strings (or an empty array).")

    return {**snapshot, "is_current": edition == today}


def register(server: MCPServer) -> None:
    @server.tool(
        title="Daily AI Briefing",
        annotations=ToolAnnotations(
            read_only_hint=True, destructive_hint=False, open_world_hint=False
        ),
    )
    def get_daily_ai_briefing() -> DailyAIBriefing:
        """Read the latest saved daily AI briefing for authorized agents; takes no inputs.

        Returns edition_date, covers_date, timezone (America/New_York), generated_at
        (UTC), briefing_markdown, source_urls, source_access_limitations, and is_current.
        The snapshot is committed on the Catalog publication Git branch and shared
        identically with authorized callers, except for invocation-computed freshness.
        Today's edition covers yesterday's New York calendar day. Preserve the actual
        saved dates, timezone, generated_at, and returned freshness when presenting it.
        Before today's publication, the prior snapshot is returned unchanged with
        is_current=false; never relabel an older edition as today's. Freshness is
        recomputed on every call using current UTC time converted to America/New_York.
        Reads only bundled latest.json: no network, research, generation, publication,
        scheduling, or writes. Missing, malformed, or invalid snapshots raise a tool
        error instead of producing a fallback briefing.
        """
        return _read_briefing()
