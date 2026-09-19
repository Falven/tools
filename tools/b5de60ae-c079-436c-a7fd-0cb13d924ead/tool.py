"""Artifact verification with explicit evidence and honest sandbox boundaries."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = ["verify_artifact"]


_TOOL_VERSION = "1.0.0"
_MAX_FILES = 100
_MAX_FILE_BYTES = 1_000_000
_MAX_ARTIFACT_BYTES = 4_000_000
_MAX_CRITERIA = 40
_MAX_READ_BYTES = 2_000_000
_MAX_HASH_BYTES = 16_000_000
_MAX_LOG_BYTES = 128_000
_MAX_TOTAL_SECONDS = 60.0


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize_path(raw_path: Any, *, allow_dot: bool = False) -> str:
    if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
        raise ValueError("path must be a non-empty string without NUL bytes")
    if raw_path == ".":
        if allow_dot:
            return "."
        raise ValueError("path must name a file or directory below the workspace")
    if "\\" in raw_path:
        raise ValueError("paths must use POSIX '/' separators")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("path must be relative and cannot contain '.' or '..'")
    normalized = str(path)
    if len(normalized) > 240:
        raise ValueError("path is longer than 240 characters")
    return normalized


def _normalize_artifact(artifact: dict[str, str] | str) -> dict[str, str]:
    if isinstance(artifact, str):
        artifact = {"artifact.txt": artifact}
    if not isinstance(artifact, dict) or not artifact:
        raise ValueError("artifact must be a non-empty string or file-path-to-text mapping")
    if len(artifact) > _MAX_FILES:
        raise ValueError(f"artifact exceeds the {_MAX_FILES}-file limit")

    normalized: dict[str, str] = {}
    total = 0
    for raw_path, content in artifact.items():
        path = _normalize_path(raw_path)
        if path in normalized:
            raise ValueError(f"duplicate normalized artifact path: {path}")
        if not isinstance(content, str):
            raise TypeError(f"artifact file {path!r} must contain UTF-8 text")
        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_FILE_BYTES:
            raise ValueError(f"artifact file {path!r} exceeds {_MAX_FILE_BYTES} bytes")
        total += len(encoded)
        if total > _MAX_ARTIFACT_BYTES:
            raise ValueError(f"artifact exceeds {_MAX_ARTIFACT_BYTES} total bytes")
        normalized[path] = content
    return dict(sorted(normalized.items()))


def _write_artifact(workspace: Path, artifact: dict[str, str]) -> None:
    for relative_path, content in artifact.items():
        target = workspace.joinpath(*PurePosixPath(relative_path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")


def _safe_path(workspace: Path, raw_path: Any, *, allow_missing: bool = False) -> Path:
    relative_path = _normalize_path(raw_path)
    current = workspace
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlinks are not followed by the verifier")
        if not current.exists():
            if allow_missing:
                return current
            raise FileNotFoundError(relative_path)
    resolved_workspace = workspace.resolve()
    resolved_current = current.resolve()
    if resolved_current != resolved_workspace and resolved_workspace not in resolved_current.parents:
        raise ValueError("path escapes the artifact workspace")
    return current


def _read_text_file(workspace: Path, raw_path: Any) -> tuple[str, Path]:
    path = _safe_path(workspace, raw_path)
    if not path.is_file():
        raise ValueError("path is not a regular file")
    size = path.stat().st_size
    if size > _MAX_READ_BYTES:
        raise ValueError(f"file exceeds the {_MAX_READ_BYTES}-byte inspection limit")
    try:
        return path.read_text(encoding="utf-8"), path
    except UnicodeDecodeError as exc:
        raise ValueError("file is not valid UTF-8 text") from exc


def _file_sha256(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError("path is not a regular non-symlink file")
    if path.stat().st_size > _MAX_HASH_BYTES:
        raise ValueError(f"file exceeds the {_MAX_HASH_BYTES}-byte hashing limit")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(workspace: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    omitted = 0
    for path in sorted(workspace.rglob("*")):
        relative = path.relative_to(workspace).as_posix()
        if path.is_symlink():
            files.append({"path": relative, "kind": "symlink", "verified": False})
        elif path.is_file():
            size = path.stat().st_size
            item: dict[str, Any] = {"path": relative, "kind": "file", "bytes": size}
            if size <= _MAX_HASH_BYTES:
                item["sha256"] = _file_sha256(path)
            else:
                item["sha256"] = None
                item["note"] = "hash omitted because file exceeds evidence limit"
            files.append(item)
        if len(files) >= 250:
            omitted += 1
            break
    return {"files": files, "truncated": bool(omitted)}


def _artifact_manifest(artifact: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "path": path,
            "bytes": len(content.encode("utf-8")),
            "sha256": _sha256(content.encode("utf-8")),
        }
        for path, content in artifact.items()
    ]


def _limited_argv(
    argv: list[str], limiter: str | None, timeout_seconds: float, memory_limit_mb: int
) -> list[str]:
    if limiter is None:
        return argv
    memory_bytes = memory_limit_mb * 1024 * 1024
    cpu_soft = max(1, int(timeout_seconds + 0.999))
    return [
        limiter,
        f"--cpu={cpu_soft}:{cpu_soft + 1}",
        f"--as={memory_bytes}:{memory_bytes}",
        "--fsize=2000000:2000000",
        "--nofile=64:64",
        "--nproc=128:128",
        "--core=0:0",
        "--",
        *argv,
    ]


def _run_process(
    argv: list[str],
    timeout_seconds: float,
    memory_limit_mb: int,
    limiter: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                _limited_argv(argv, limiter, timeout_seconds, memory_limit_mb),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            return {
                "spawn_error": f"{type(exc).__name__}: {exc}",
                "duration_ms": round((time.monotonic() - started) * 1000),
            }

        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            exit_code = process.wait()

        def collect(handle: Any) -> tuple[str, bool, int]:
            size = handle.tell()
            handle.seek(0)
            data = handle.read(_MAX_LOG_BYTES)
            return data.decode("utf-8", errors="replace"), size > _MAX_LOG_BYTES, size

        stdout, stdout_truncated, stdout_bytes = collect(stdout_file)
        stderr, stderr_truncated, stderr_bytes = collect(stderr_file)
        return {
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "stdout": stdout,
            "stderr": stderr,
            "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }


def _bwrap_base(bwrap: str, workspace: Path, working_directory: str) -> list[str]:
    command = [
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
    ]
    for system_path in ("/usr", "/usr/local", "/bin", "/lib", "/lib64"):
        if Path(system_path).exists():
            command.extend(["--ro-bind", system_path, system_path])
    for system_file in ("/etc/ld.so.cache", "/etc/localtime"):
        if Path(system_file).is_file():
            command.extend(["--ro-bind", system_file, system_file])
    sandbox_cwd = "/workspace"
    if working_directory != ".":
        sandbox_cwd += "/" + working_directory
    command.extend(
        [
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--ro-bind",
            str(workspace),
            "/workspace",
            "--chdir",
            sandbox_cwd,
            "--clearenv",
            "--setenv",
            "PATH",
            "/usr/local/bin:/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "TZ",
            "UTC",
            "--setenv",
            "PYTHONHASHSEED",
            "0",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "SOURCE_DATE_EPOCH",
            "0",
            "--",
        ]
    )
    return command


def _detect_sandbox(workspace: Path, memory_limit_mb: int) -> dict[str, Any]:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return {
            "kind": "none",
            "available": False,
            "reason": "bubblewrap (bwrap) is not installed; executable criteria were not run",
        }
    limiter = shutil.which("prlimit")
    if not limiter:
        return {
            "kind": "bubblewrap",
            "available": False,
            "reason": "prlimit is not installed; executable criteria were not run without resource limits",
        }
    true_path = "/usr/bin/true" if Path("/usr/bin/true").exists() else "/bin/true"
    probe = _run_process(
        _bwrap_base(bwrap, workspace, ".") + [true_path],
        timeout_seconds=3.0,
        memory_limit_mb=memory_limit_mb,
        limiter=limiter,
    )
    if probe.get("exit_code") != 0 or probe.get("timed_out") or probe.get("spawn_error"):
        detail = probe.get("spawn_error") or probe.get("stderr") or "sandbox probe failed"
        return {
            "kind": "bubblewrap",
            "available": False,
            "reason": str(detail)[:2000],
        }
    version = "unknown"
    try:
        version_result = subprocess.run(
            [bwrap, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=2,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
            check=False,
        )
        version = (version_result.stdout or version_result.stderr).strip()[:200]
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "kind": "bubblewrap",
        "available": True,
        "version": version,
        "network": "disabled by a new network namespace",
        "filesystem": "artifact workspace and selected system runtime paths read-only; /tmp ephemeral",
        "process": "new PID/session namespaces plus process resource limits",
        "security_boundary": "Linux namespace sandbox, not a virtual machine",
        "_executable": bwrap,
        "_limiter": limiter,
    }


def _result(
    criterion_id: str,
    criterion_type: str,
    status: str,
    summary: str,
    *,
    outcome_class: str = "verified",
    actual: Any = None,
    expected: Any = None,
    logs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": criterion_id,
        "type": criterion_type,
        "status": status,
        "outcome_class": outcome_class,
        "summary": summary,
    }
    if expected is not None:
        result["expected"] = expected
    if actual is not None:
        result["actual"] = actual
    if logs is not None:
        result["logs"] = logs
    return result


def _require_string(criterion: dict[str, Any], key: str) -> str:
    value = criterion.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key!r} must be a string")
    return value


def _string_list(value: Any, key: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise TypeError(f"{key!r} must be a string or list of strings")


def _evaluate_static(
    workspace: Path,
    criterion_id: str,
    criterion_type: str,
    criterion: dict[str, Any],
) -> dict[str, Any]:
    path_value = criterion.get("path")

    if criterion_type in ("file_exists", "file_not_exists"):
        normalized = _normalize_path(path_value)
        path = workspace.joinpath(*PurePosixPath(normalized).parts)
        exists = os.path.lexists(path)
        if path.is_symlink():
            kind = "symlink (not followed)"
        elif path.is_dir():
            kind = "directory"
        elif path.is_file():
            kind = "file"
        elif exists:
            kind = "other"
        else:
            kind = "missing"
        expected_exists = criterion_type == "file_exists"
        passed = exists == expected_exists
        return _result(
            criterion_id,
            criterion_type,
            "pass" if passed else "fail",
            f"path {normalized!r} {'satisfied' if passed else 'did not satisfy'} {criterion_type}",
            actual={"exists": exists, "kind": kind},
            expected={"exists": expected_exists},
        )

    if criterion_type in (
        "text_contains",
        "text_not_contains",
        "text_equals",
        "json_valid",
        "python_syntax",
    ):
        text, path = _read_text_file(workspace, path_value)
        relative = path.relative_to(workspace).as_posix()

        if criterion_type in ("text_contains", "text_not_contains"):
            needle = _require_string(criterion, "text")
            case_sensitive = criterion.get("case_sensitive", True)
            if not isinstance(case_sensitive, bool):
                raise ValueError("'case_sensitive' must be a boolean")
            haystack_cmp = text if case_sensitive else text.casefold()
            needle_cmp = needle if case_sensitive else needle.casefold()
            contains = needle_cmp in haystack_cmp
            expected_contains = criterion_type == "text_contains"
            passed = contains == expected_contains
            return _result(
                criterion_id,
                criterion_type,
                "pass" if passed else "fail",
                f"text condition {'matched' if passed else 'did not match'} in {relative!r}",
                actual={"contains": contains},
                expected={"contains": expected_contains, "text": needle},
            )

        if criterion_type == "text_equals":
            expected_text = _require_string(criterion, "text")
            passed = text == expected_text
            return _result(
                criterion_id,
                criterion_type,
                "pass" if passed else "fail",
                f"text in {relative!r} {'equals' if passed else 'does not equal'} expected text",
                actual={"sha256": _sha256(text.encode("utf-8")), "bytes": len(text.encode("utf-8"))},
                expected={
                    "sha256": _sha256(expected_text.encode("utf-8")),
                    "bytes": len(expected_text.encode("utf-8")),
                },
            )

        if criterion_type == "json_valid":
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, RecursionError) as exc:
                return _result(
                    criterion_id,
                    criterion_type,
                    "fail",
                    f"{relative!r} is not valid JSON",
                    actual={"error": f"{type(exc).__name__}: {exc}"},
                    expected={"valid_json": True},
                )
            return _result(
                criterion_id,
                criterion_type,
                "pass",
                f"{relative!r} is valid JSON",
                actual={"valid_json": True, "top_level_type": type(parsed).__name__},
                expected={"valid_json": True},
            )

        try:
            compile(text, relative, "exec", dont_inherit=True)
        except (SyntaxError, ValueError, OverflowError) as exc:
            return _result(
                criterion_id,
                criterion_type,
                "fail",
                f"{relative!r} does not compile as Python",
                actual={
                    "error": f"{type(exc).__name__}: {exc}",
                    "line": getattr(exc, "lineno", None),
                    "offset": getattr(exc, "offset", None),
                },
                expected={"python_compiles": True},
            )
        return _result(
            criterion_id,
            criterion_type,
            "pass",
            f"{relative!r} compiles as Python",
            actual={"python_compiles": True},
            expected={"python_compiles": True},
        )

    if criterion_type == "sha256":
        expected_digest = _require_string(criterion, "sha256").lower()
        if len(expected_digest) != 64 or any(char not in "0123456789abcdef" for char in expected_digest):
            raise ValueError("'sha256' must be a 64-character hexadecimal digest")
        path = _safe_path(workspace, path_value)
        actual_digest = _file_sha256(path)
        passed = actual_digest == expected_digest
        return _result(
            criterion_id,
            criterion_type,
            "pass" if passed else "fail",
            f"SHA-256 for {_normalize_path(path_value)!r} {'matched' if passed else 'did not match'}",
            actual={"sha256": actual_digest},
            expected={"sha256": expected_digest},
        )

    if criterion_type == "file_size":
        path = _safe_path(workspace, path_value)
        if not path.is_file():
            raise ValueError("path is not a regular file")
        size = path.stat().st_size
        minimum = criterion.get("min_bytes", 0)
        maximum = criterion.get("max_bytes", _MAX_HASH_BYTES)
        if (
            not isinstance(minimum, int)
            or isinstance(minimum, bool)
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or minimum < 0
            or maximum < minimum
        ):
            raise ValueError("'min_bytes' and 'max_bytes' must be valid non-negative integer bounds")
        passed = minimum <= size <= maximum
        return _result(
            criterion_id,
            criterion_type,
            "pass" if passed else "fail",
            f"file size {'is' if passed else 'is not'} within bounds",
            actual={"bytes": size},
            expected={"min_bytes": minimum, "max_bytes": maximum},
        )

    raise ValueError(
        "unsupported criterion type; use file_exists, file_not_exists, text_contains, "
        "text_not_contains, text_equals, json_valid, python_syntax, sha256, file_size, or command"
    )


def _evaluate_command(
    workspace: Path,
    criterion_id: str,
    criterion: dict[str, Any],
    sandbox: dict[str, Any],
    timeout_seconds: float,
    memory_limit_mb: int,
) -> dict[str, Any]:
    if not sandbox.get("available"):
        return _result(
            criterion_id,
            "command",
            "untested",
            "command was not executed because a secure sandbox backend is unavailable",
            outcome_class="untested",
            actual={"sandbox_reason": sandbox.get("reason", "unavailable")},
        )

    argv = criterion.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or len(argv) > 64
        or not all(isinstance(arg, str) and arg and "\x00" not in arg and len(arg) <= 4096 for arg in argv)
    ):
        raise TypeError("'argv' must be a non-empty list of at most 64 non-empty strings")
    working_directory = _normalize_path(criterion.get("working_directory", "."), allow_dot=True)
    work_path = workspace if working_directory == "." else _safe_path(workspace, working_directory)
    if not work_path.is_dir():
        raise ValueError("'working_directory' must name an existing directory")

    expected_exit_code = criterion.get("expected_exit_code", 0)
    if not isinstance(expected_exit_code, int) or isinstance(expected_exit_code, bool):
        raise TypeError("'expected_exit_code' must be an integer")
    stdout_contains = _string_list(criterion.get("stdout_contains"), "stdout_contains")
    stderr_contains = _string_list(criterion.get("stderr_contains"), "stderr_contains")
    stdout_not_contains = _string_list(criterion.get("stdout_not_contains"), "stdout_not_contains")
    stderr_not_contains = _string_list(criterion.get("stderr_not_contains"), "stderr_not_contains")

    bwrap = sandbox["_executable"]
    execution = _run_process(
        _bwrap_base(bwrap, workspace, working_directory) + argv,
        timeout_seconds=timeout_seconds,
        memory_limit_mb=memory_limit_mb,
        limiter=sandbox["_limiter"],
    )
    if execution.get("spawn_error"):
        return _result(
            criterion_id,
            "command",
            "untested",
            "sandbox process could not be started",
            outcome_class="untested",
            actual={"error": execution["spawn_error"]},
        )

    checks = {
        "exit_code": execution.get("exit_code") == expected_exit_code,
        "not_timed_out": not execution.get("timed_out", False),
        "stdout_contains": all(item in execution.get("stdout", "") for item in stdout_contains),
        "stderr_contains": all(item in execution.get("stderr", "") for item in stderr_contains),
        "stdout_not_contains": all(item not in execution.get("stdout", "") for item in stdout_not_contains),
        "stderr_not_contains": all(item not in execution.get("stderr", "") for item in stderr_not_contains),
    }
    passed = all(checks.values())
    logs = {
        key: execution[key]
        for key in (
            "stdout",
            "stderr",
            "stdout_bytes",
            "stderr_bytes",
            "stdout_truncated",
            "stderr_truncated",
            "duration_ms",
        )
    }
    return _result(
        criterion_id,
        "command",
        "pass" if passed else "fail",
        f"sandboxed command {'satisfied' if passed else 'did not satisfy'} its expectations",
        actual={
            "argv": argv,
            "working_directory": working_directory,
            "exit_code": execution.get("exit_code"),
            "timed_out": execution.get("timed_out"),
            "checks": checks,
        },
        expected={
            "exit_code": expected_exit_code,
            "stdout_contains": stdout_contains,
            "stderr_contains": stderr_contains,
            "stdout_not_contains": stdout_not_contains,
            "stderr_not_contains": stderr_not_contains,
        },
        logs=logs,
    )


def _iteration_comparison(
    prior_result: dict[str, Any] | None, current_results: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if prior_result is None:
        return None
    if not isinstance(prior_result, dict):
        return {
            "source": "caller_supplied_unverified",
            "error": "prior_result was not an object and could not be compared",
        }
    prior_criteria = prior_result.get("criteria", [])
    prior_statuses: dict[str, Any] = {}
    if isinstance(prior_criteria, list):
        for item in prior_criteria:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                prior_statuses[item["id"]] = item.get("status")
    transitions = [
        {
            "id": item["id"],
            "prior_claimed_status": prior_statuses.get(item["id"], "not_provided"),
            "current_status": item["status"],
            "current_outcome_class": item["outcome_class"],
        }
        for item in current_results
    ]
    evidence = prior_result.get("evidence")
    prior_evidence_id = evidence.get("evidence_id") if isinstance(evidence, dict) else None
    return {
        "source": "caller_supplied_unverified",
        "prior_evidence_id": prior_evidence_id,
        "transitions": transitions,
        "caveat": (
            "The current run is verified by this invocation. Prior statuses are comparison claims "
            "only because this stateless tool does not authenticate or retrieve earlier evidence."
        ),
    }


def verify_artifact(
    artifact: dict[str, str] | str,
    success_criteria: list[dict[str, Any]],
    timeout_seconds: int = 10,
    memory_limit_mb: int = 256,
    iteration_label: str | None = None,
    prior_result: dict[str, Any] | None = None,
    declared_assumptions: list[str] | None = None,
) -> dict[str, Any]:
    """Test a text artifact bundle against explicit criteria and return auditable evidence.

    Use this when an agent has generated or revised files and needs pass/fail evidence rather
    than a self-assessment. `artifact` is either one string (stored as `artifact.txt`) or a
    mapping of relative POSIX file paths to UTF-8 text. `success_criteria` is an ordered list of
    objects with a unique optional `id` and a `type`. Supported static types are `file_exists`,
    `file_not_exists`, `text_contains`, `text_not_contains`, `text_equals`, `json_valid`,
    `python_syntax`, `sha256`, and `file_size`. Their relevant fields are `path`, `text`,
    `case_sensitive`, `sha256`, `min_bytes`, and `max_bytes`.

    A `command` criterion runs without a shell unless its `argv` explicitly invokes one. It
    accepts `argv`, optional `working_directory`, `expected_exit_code` (default 0), and string
    or string-list expectations named `stdout_contains`, `stderr_contains`,
    `stdout_not_contains`, and `stderr_not_contains`. Commands run only when Linux bubblewrap
    passes a runtime probe: networking is disabled, the artifact workspace is the only writable
    mount, the environment is scrubbed, and CPU, memory, file, process, and output limits apply.
    If that secure backend is unavailable, command behavior is returned as `untested` rather
    than guessed or run directly on the host. The sandbox is a namespace boundary, not a VM.

    Criteria run in order, but the submitted artifact is mounted read-only during commands.
    Commands that need scratch space may use `/tmp`; generated scratch files are not available to
    later static criteria. `timeout_seconds` is per command (1-30 seconds), while the whole
    invocation has a 60-second command budget; `memory_limit_mb` is 32-512. For iterative repair,
    pass the previous returned object as `prior_result`; comparison data is explicitly labeled
    caller-supplied and unverified because the tool is stateless. Put any known but unproven
    claims in `declared_assumptions`.

    Returns overall `pass`, `fail`, `incomplete`, or `error`; per-criterion verified/untested
    outcomes; bounded stdout/stderr logs; pre/post file manifests and hashes; deterministic run
    and evidence fingerprints; iteration transitions; declared assumptions; and limitations.
    No artifact or evidence is persisted. A pass verifies only the submitted criteria in the
    reported sandbox and does not imply unspecified behavior, external integration, UI, security,
    performance, or production correctness.
    """
    started = time.monotonic()
    try:
        normalized_artifact = _normalize_artifact(artifact)
        if not isinstance(success_criteria, list) or not success_criteria:
            raise ValueError("success_criteria must be a non-empty list")
        if len(success_criteria) > _MAX_CRITERIA:
            raise ValueError(f"success_criteria exceeds the {_MAX_CRITERIA}-criterion limit")
        if (
            not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or not 1 <= timeout_seconds <= 30
        ):
            raise ValueError("timeout_seconds must be an integer from 1 to 30")
        if (
            not isinstance(memory_limit_mb, int)
            or isinstance(memory_limit_mb, bool)
            or not 32 <= memory_limit_mb <= 512
        ):
            raise ValueError("memory_limit_mb must be an integer from 32 to 512")
        if iteration_label is not None and not isinstance(iteration_label, str):
            raise ValueError("iteration_label must be a string or null")
        if declared_assumptions is None:
            declared_assumptions = []
        if not isinstance(declared_assumptions, list) or not all(
            isinstance(item, str) for item in declared_assumptions
        ):
            raise ValueError("declared_assumptions must be a list of strings")
    except (TypeError, ValueError) as exc:
        return {
            "tool_version": _TOOL_VERSION,
            "overall_status": "error",
            "success": False,
            "complete": False,
            "input_error": str(exc),
            "criteria": [],
            "verified_outcomes": [],
            "untested_behavior": ["No tests ran because the submitted input was invalid."],
            "assumptions": [],
        }

    criteria_for_fingerprint: list[Any] = []
    artifact_digest = _sha256(_canonical_json(normalized_artifact))
    criteria_digest = _sha256(_canonical_json(success_criteria))

    with tempfile.TemporaryDirectory(prefix="artifact-verifier-") as temporary_directory:
        workspace = Path(temporary_directory)
        _write_artifact(workspace, normalized_artifact)
        pre_manifest = _artifact_manifest(normalized_artifact)
        sandbox = _detect_sandbox(workspace, memory_limit_mb)
        public_sandbox = {key: value for key, value in sandbox.items() if not key.startswith("_")}

        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        command_deadline = time.monotonic() + _MAX_TOTAL_SECONDS

        for index, raw_criterion in enumerate(success_criteria, start=1):
            fallback_id = f"criterion_{index}"
            if not isinstance(raw_criterion, dict):
                results.append(
                    _result(
                        fallback_id,
                        "invalid",
                        "error",
                        "criterion must be an object",
                        outcome_class="error",
                    )
                )
                criteria_for_fingerprint.append(raw_criterion)
                continue

            criterion = dict(raw_criterion)
            criterion_id = criterion.get("id", fallback_id)
            criterion_type = criterion.get("type")
            if not isinstance(criterion_id, str) or not criterion_id or len(criterion_id) > 100:
                criterion_id = fallback_id
                results.append(
                    _result(
                        criterion_id,
                        str(criterion_type or "invalid"),
                        "error",
                        "criterion id must be a non-empty string of at most 100 characters",
                        outcome_class="error",
                    )
                )
                criteria_for_fingerprint.append(criterion)
                continue
            if criterion_id in seen_ids:
                results.append(
                    _result(
                        criterion_id,
                        str(criterion_type or "invalid"),
                        "error",
                        "criterion id is duplicated",
                        outcome_class="error",
                    )
                )
                criteria_for_fingerprint.append(criterion)
                continue
            seen_ids.add(criterion_id)
            if not isinstance(criterion_type, str):
                results.append(
                    _result(
                        criterion_id,
                        "invalid",
                        "error",
                        "criterion type must be a string",
                        outcome_class="error",
                    )
                )
                criteria_for_fingerprint.append(criterion)
                continue

            criteria_for_fingerprint.append(criterion)
            try:
                if criterion_type == "command":
                    remaining = command_deadline - time.monotonic()
                    if remaining <= 0:
                        result = _result(
                            criterion_id,
                            "command",
                            "untested",
                            "command was not run because the invocation command budget was exhausted",
                            outcome_class="untested",
                        )
                    else:
                        result = _evaluate_command(
                            workspace,
                            criterion_id,
                            criterion,
                            sandbox,
                            timeout_seconds=min(float(timeout_seconds), remaining),
                            memory_limit_mb=memory_limit_mb,
                        )
                else:
                    result = _evaluate_static(workspace, criterion_id, criterion_type, criterion)
            except (TypeError, ValueError, FileNotFoundError, OSError) as exc:
                result = _result(
                    criterion_id,
                    criterion_type,
                    "error",
                    f"criterion could not be evaluated: {type(exc).__name__}: {exc}",
                    outcome_class="error",
                )
            results.append(result)

        post_manifest = _manifest(workspace)

    statuses = [item["status"] for item in results]
    complete = bool(results) and all(item["outcome_class"] == "verified" for item in results)
    if "fail" in statuses:
        overall_status = "fail"
    elif statuses and all(status == "pass" for status in statuses):
        overall_status = "pass"
    elif "error" in statuses:
        overall_status = "error"
    else:
        overall_status = "incomplete"
    success = overall_status == "pass" and complete

    run_fingerprint_payload = {
        "tool_version": _TOOL_VERSION,
        "artifact_sha256": artifact_digest,
        "criteria_sha256": criteria_digest,
        "criteria": criteria_for_fingerprint,
        "limits": {
            "timeout_seconds": timeout_seconds,
            "memory_limit_mb": memory_limit_mb,
            "total_command_budget_seconds": _MAX_TOTAL_SECONDS,
        },
        "sandbox": public_sandbox,
    }
    run_fingerprint = _sha256(_canonical_json(run_fingerprint_payload))
    evidence_payload = {
        "run_fingerprint": run_fingerprint,
        "criteria": [
            {
                key: (
                    {log_key: log_value for log_key, log_value in value.items() if log_key != "duration_ms"}
                    if key == "logs" and isinstance(value, dict)
                    else value
                )
                for key, value in item.items()
            }
            for item in results
        ],
        "post_manifest": post_manifest,
    }
    evidence_id = _sha256(_canonical_json(evidence_payload))

    verified_outcomes = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in results
        if item["outcome_class"] == "verified"
    ]
    untested_behavior = [
        {"id": item["id"], "summary": item["summary"]}
        for item in results
        if item["outcome_class"] == "untested"
    ]
    if not any(item["type"] == "command" for item in results):
        untested_behavior.append(
            {
                "id": "runtime_behavior",
                "summary": "No executable criterion was submitted; runtime behavior was not tested.",
            }
        )

    assumptions = [
        {"claim": item, "status": "assumption_not_verified"} for item in declared_assumptions
    ]
    assumptions.append(
        {
            "claim": "The submitted success criteria completely represent the caller's real requirements.",
            "status": "assumption_not_verified",
        }
    )

    return {
        "tool_version": _TOOL_VERSION,
        "iteration_label": iteration_label,
        "overall_status": overall_status,
        "success": success,
        "complete": complete,
        "summary": {
            "passed": statuses.count("pass"),
            "failed": statuses.count("fail"),
            "errors": statuses.count("error"),
            "untested": statuses.count("untested"),
            "duration_ms": round((time.monotonic() - started) * 1000),
        },
        "criteria": results,
        "verified_outcomes": verified_outcomes,
        "untested_behavior": untested_behavior,
        "assumptions": assumptions,
        "iteration_comparison": _iteration_comparison(prior_result, results),
        "sandbox": public_sandbox,
        "evidence": {
            "evidence_id": evidence_id,
            "run_fingerprint": run_fingerprint,
            "artifact_sha256": artifact_digest,
            "criteria_sha256": criteria_digest,
            "input_manifest": pre_manifest,
            "post_run_manifest": post_manifest,
            "normalized_criteria": criteria_for_fingerprint,
            "reproduction": (
                "Resubmit files matching input_manifest hashes with normalized_criteria and the "
                "same limits. Compare run_fingerprint for equivalent inputs/environment and "
                "evidence_id for equivalent observed results/logs."
            ),
            "persisted": False,
        },
        "limitations": [
            "A pass covers only the submitted criteria; unspecified behavior remains untested.",
            "Command isolation uses Linux namespaces when available and is not a virtual machine.",
            "System runtime files are read-only but may differ across ToolForge deployments.",
            (
                "Timing, concurrency, external services, browser/UI behavior, and production load "
                "are untested unless explicit executable criteria cover them."
            ),
            "Logs are UTF-8-decoded with replacement and truncated after 128000 bytes per stream.",
            "Prior results are not authenticated or persisted by this stateless tool.",
        ],
    }
