"""Tests for SandboxRecorder."""

from pysandbox.engine.recorder import SandboxRecorder


def test_start_creates_session():
    rec = SandboxRecorder()
    session = rec.start("sb-1", name="my-run")
    assert session.active
    assert session.name == "my-run"
    assert rec.is_active("sb-1")


def test_stop_flags_inactive():
    rec = SandboxRecorder()
    rec.start("sb-1")
    rec.stop("sb-1")
    assert not rec.is_active("sb-1")
    session = rec.get("sb-1")
    assert session is not None
    assert session.stopped_at is not None


def test_stop_on_missing_session_returns_none():
    rec = SandboxRecorder()
    assert rec.stop("sb-missing") is None


def test_record_call_appends_when_active():
    rec = SandboxRecorder()
    rec.start("sb-1")
    assert rec.record_call(
        "sb-1", "sql_query", {"query": "SELECT 1"}, "1\n", status="ok",
    ) is True
    session = rec.get("sb-1")
    assert len(session.calls) == 1
    assert session.calls[0].tool == "sql_query"
    assert session.calls[0].status == "ok"


def test_record_call_no_op_when_inactive():
    rec = SandboxRecorder()
    # No session → no-op.
    assert rec.record_call("sb-1", "sql_query", {}, "x") is False
    # Stopped session → also no-op.
    rec.start("sb-1")
    rec.stop("sb-1")
    assert rec.record_call("sb-1", "sql_query", {}, "x") is False


def test_record_call_truncates_huge_output():
    rec = SandboxRecorder()
    rec.start("sb-1")
    big = "x" * 10_000
    rec.record_call("sb-1", "tool", {}, big)
    assert len(rec.get("sb-1").calls[0].result) <= 4000


def test_annotate_last_attaches_note():
    rec = SandboxRecorder()
    rec.start("sb-1")
    rec.record_call("sb-1", "t1", {}, "ok")
    assert rec.annotate_last("sb-1", "this fixed the stuck lock") is True
    assert rec.get("sb-1").calls[-1].note == "this fixed the stuck lock"


def test_annotate_last_fails_with_no_calls():
    rec = SandboxRecorder()
    rec.start("sb-1")
    assert rec.annotate_last("sb-1", "n/a") is False


def test_preserve_option_keeps_session():
    rec = SandboxRecorder()
    s1 = rec.start("sb-1", name="original")
    rec.record_call("sb-1", "t", {}, "ok")
    s2 = rec.start("sb-1", preserve=True)
    # Same session, still has calls.
    assert s1.started_at == s2.started_at
    assert len(rec.get("sb-1").calls) == 1


def test_to_dict_has_expected_shape():
    rec = SandboxRecorder()
    rec.start("sb-1", name="runbook")
    rec.record_call("sb-1", "t1", {"k": "v"}, "ok", status="ok", duration_ms=42)
    d = rec.to_dict("sb-1")
    assert d is not None
    assert d["sandbox_id"] == "sb-1"
    assert d["name"] == "runbook"
    assert d["call_count"] == 1
    assert d["calls"][0]["tool"] == "t1"
    assert d["calls"][0]["duration_ms"] == 42


def test_to_pyverify_spec_emits_replay_scenario():
    rec = SandboxRecorder()
    rec.start("sb-1", name="fix-stale-lock")
    rec.record_call("sb-1", "redis_scan", {"pattern": "lock:*"}, "lock:stale", status="ok")
    rec.record_call("sb-1", "redis_delete", {"key": "lock:stale"}, "1", status="ok")
    spec = rec.to_pyverify_spec("sb-1")
    assert spec is not None
    assert spec["name"] == "fix-stale-lock"
    assert len(spec["scenarios"]) == 1
    scenario = spec["scenarios"][0]
    assert scenario["name"] == "replay"
    assert len(scenario["steps"]) == 2
    # Successful steps get expect_no_error.
    assert scenario["steps"][0]["expect_no_error"] is True


def test_to_pyverify_uses_note_as_step_name():
    rec = SandboxRecorder()
    rec.start("sb-1")
    rec.record_call("sb-1", "redis_delete", {"key": "x"}, "1")
    rec.annotate_last("sb-1", "clear stale lock")
    spec = rec.to_pyverify_spec("sb-1")
    assert spec["scenarios"][0]["steps"][0]["name"] == "clear stale lock"


def test_to_markdown_has_expected_headings():
    rec = SandboxRecorder()
    rec.start("sb-1", name="incident-123")
    rec.record_call("sb-1", "sql_query", {"query": "SELECT 1"}, "1\n", plugin_name="db")
    md = rec.to_markdown("sb-1")
    assert md is not None
    assert "# incident-123" in md
    assert "### 1." in md
    assert "`sql_query`" in md
    assert "`db`" in md


def test_missing_sandbox_returns_none_everywhere():
    rec = SandboxRecorder()
    assert rec.get("missing") is None
    assert rec.to_dict("missing") is None
    assert rec.to_pyverify_spec("missing") is None
    assert rec.to_markdown("missing") is None


def test_discard_removes_session():
    rec = SandboxRecorder()
    rec.start("sb-1")
    rec.discard("sb-1")
    assert rec.get("sb-1") is None
