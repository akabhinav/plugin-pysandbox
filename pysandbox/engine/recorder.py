"""Sandbox Recorder — capture agent tool invocations and export as runbooks.

The recorder is a passive observer: it listens for `agent.tool_invoked`
events (emitted by the API layer just after a tool handler runs) and
appends them to a per-sandbox session log. When the user asks to export,
we serialize the log as a structured runbook — either:

  * YAML that the pyverify runner can replay as a scenario spec, or
  * Markdown with pretty step-by-step narrative for incident reports.

This is intentionally retrospective: we only capture tool calls the user
ran, so the resulting runbook is executable documentation of the exact
sequence that fixed (or caused) the incident — no more "it was something
like `kubectl scale` I think".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RecordedCall:
    """One tool invocation captured during a recording session."""

    timestamp: str
    tool: str
    args: dict[str, Any]
    result: str
    status: str  # "ok" or "error"
    duration_ms: int = 0
    plugin_name: str | None = None
    note: str | None = None


@dataclass
class RecordingSession:
    """Per-sandbox recording state."""

    sandbox_id: str
    started_at: str
    active: bool = True
    calls: list[RecordedCall] = field(default_factory=list)
    name: str | None = None  # set by start()
    stopped_at: str | None = None


class SandboxRecorder:
    """Owns the set of active recordings and exposes CRUD + export.

    Multiple sandboxes can record simultaneously; each has its own session.
    A sandbox can only have one active session at a time. Re-starting
    replaces the old session unless the caller passes `preserve=True`,
    which is useful for continuing a recording across API restarts.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, RecordingSession] = {}

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(
        self, sandbox_id: str, name: str | None = None, preserve: bool = False,
    ) -> RecordingSession:
        """Start (or restart) a recording for a sandbox."""
        existing = self._sessions.get(sandbox_id)
        if existing and preserve:
            existing.active = True
            return existing
        session = RecordingSession(
            sandbox_id=sandbox_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            name=name,
        )
        self._sessions[sandbox_id] = session
        return session

    def stop(self, sandbox_id: str) -> RecordingSession | None:
        session = self._sessions.get(sandbox_id)
        if session is None:
            return None
        session.active = False
        session.stopped_at = datetime.now(timezone.utc).isoformat()
        return session

    def discard(self, sandbox_id: str) -> None:
        """Drop the recording entirely."""
        self._sessions.pop(sandbox_id, None)

    def get(self, sandbox_id: str) -> RecordingSession | None:
        return self._sessions.get(sandbox_id)

    def is_active(self, sandbox_id: str) -> bool:
        session = self._sessions.get(sandbox_id)
        return bool(session and session.active)

    # ── recording ──────────────────────────────────────────────────────

    def record_call(
        self,
        sandbox_id: str,
        tool: str,
        args: dict[str, Any],
        result: str,
        status: str = "ok",
        duration_ms: int = 0,
        plugin_name: str | None = None,
        note: str | None = None,
    ) -> bool:
        """Append a tool invocation to the active session. Returns True if recorded."""
        session = self._sessions.get(sandbox_id)
        if session is None or not session.active:
            return False
        session.calls.append(RecordedCall(
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool=tool,
            args=dict(args),
            result=result[:4000],  # cap large outputs
            status=status,
            duration_ms=duration_ms,
            plugin_name=plugin_name,
            note=note,
        ))
        return True

    def annotate_last(self, sandbox_id: str, note: str) -> bool:
        """Attach a human note to the most recent captured call."""
        session = self._sessions.get(sandbox_id)
        if not session or not session.calls:
            return False
        session.calls[-1].note = note
        return True

    # ── export ─────────────────────────────────────────────────────────

    def to_dict(self, sandbox_id: str) -> dict[str, Any] | None:
        session = self._sessions.get(sandbox_id)
        if session is None:
            return None
        return {
            "sandbox_id": session.sandbox_id,
            "name": session.name,
            "started_at": session.started_at,
            "stopped_at": session.stopped_at,
            "active": session.active,
            "call_count": len(session.calls),
            "calls": [
                {
                    "timestamp": c.timestamp,
                    "tool": c.tool,
                    "args": c.args,
                    "result": c.result,
                    "status": c.status,
                    "duration_ms": c.duration_ms,
                    "plugin_name": c.plugin_name,
                    "note": c.note,
                }
                for c in session.calls
            ],
        }

    def to_pyverify_spec(
        self, sandbox_id: str, spec_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Render the recording as a pyverify spec dict.

        Every captured call becomes a step; we drop `expect_*` assertions
        because we don't know what the user's intent was — the exported
        spec is intended as a starting point the engineer can refine.
        Successful calls become steps with `expect_no_error: true`.
        """
        session = self._sessions.get(sandbox_id)
        if session is None:
            return None
        steps = []
        for c in session.calls:
            step: dict[str, Any] = {
                "name": c.note or f"{c.tool}",
                "tool": c.tool,
                "args": c.args,
            }
            if c.status == "ok":
                step["expect_no_error"] = True
            steps.append(step)
        return {
            "name": spec_name or session.name or f"runbook-{session.sandbox_id[:8]}",
            "scenarios": [
                {
                    "name": "replay",
                    "steps": steps,
                },
            ],
        }

    def to_markdown(self, sandbox_id: str) -> str | None:
        """Render the recording as a human-readable markdown runbook."""
        session = self._sessions.get(sandbox_id)
        if session is None:
            return None
        lines = []
        title = session.name or f"Runbook for sandbox {session.sandbox_id[:8]}"
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"- Recorded: {session.started_at}")
        if session.stopped_at:
            lines.append(f"- Stopped:  {session.stopped_at}")
        lines.append(f"- Calls:    {len(session.calls)}")
        lines.append("")
        lines.append("## Steps")
        lines.append("")
        for i, c in enumerate(session.calls, 1):
            heading = c.note or c.tool
            lines.append(f"### {i}. {heading}")
            lines.append("")
            lines.append(f"- **tool**: `{c.tool}`")
            if c.plugin_name:
                lines.append(f"- **plugin**: `{c.plugin_name}`")
            lines.append(f"- **args**: `{c.args}`")
            lines.append(f"- **status**: {c.status}")
            if c.result:
                result_snippet = c.result.strip()
                if len(result_snippet) > 200:
                    result_snippet = result_snippet[:200] + "..."
                lines.append("")
                lines.append("```")
                lines.append(result_snippet)
                lines.append("```")
            lines.append("")
        return "\n".join(lines)
