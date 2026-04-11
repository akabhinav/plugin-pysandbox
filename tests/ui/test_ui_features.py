"""End-to-end UI smoke tests for the 10 new features.

Uses `streamlit.testing.v1.AppTest` to run ui/app.py programmatically
against a REAL live API (127.0.0.1:18080) and a REAL sandbox with real
containers.

These tests:
  * boot the Streamlit app in-process and inspect its widget tree
  * set session_state to force specific routes (page + sandbox_id)
  * assert no exceptions surface from any of the new code paths
  * for page/tab widgets that should only appear on certain routes,
    assert their presence

The goal isn't to cover every click path — that's a browser-based job —
but to guarantee every new helper function in ui/features.py runs
against a real API without raising.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

# Make `import features` work from the test module.
UI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ui"))
sys.path.insert(0, UI_DIR)

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:18080")
TEST_SANDBOX_ID = os.getenv("TEST_SANDBOX_ID", "")


# ── Preconditions ──────────────────────────────────────────────────────

def _api_alive() -> bool:
    try:
        return httpx.get(f"{API_BASE}/health", timeout=2).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _api_alive() or not TEST_SANDBOX_ID,
    reason="requires a running pysandbox API + TEST_SANDBOX_ID env var",
)


# ── AppTest helpers ────────────────────────────────────────────────────

def _fresh_app():
    """Return a new AppTest pointed at ui/app.py with a long timeout.

    The 60s timeout handles slow API calls (container creation, volume
    copies) that the UI surfaces synchronously.
    """
    from streamlit.testing.v1 import AppTest

    app_path = os.path.join(UI_DIR, "app.py")
    at = AppTest.from_file(app_path, default_timeout=60)
    # Make sure features.py + httpx pick up the same API we're testing.
    at.session_state["page"] = "dashboard"
    return at


def _route(at, page: str, sandbox_id: str | None = None):
    """Force the router onto a specific page before calling `.run()`."""
    at.session_state["page"] = page
    if sandbox_id:
        at.session_state["sandbox_id"] = sandbox_id
    return at


def _run_and_assert_clean(at):
    """Run the app and fail if any exceptions or errors rendered."""
    result = at.run()
    # Streamlit collects both Python exceptions (exception blocks) and
    # st.error()/st.warning() calls. We only fail on the hard ones.
    if result.exception:
        msgs = [str(e) for e in result.exception]
        raise AssertionError(f"Streamlit raised: {msgs}")
    return result


# ── Feature 1: Devcontainer export ────────────────────────────────────

def test_devcontainer_tab_renders_without_error():
    at = _fresh_app()
    _route(at, "sandbox_detail", TEST_SANDBOX_ID)
    result = _run_and_assert_clean(at)
    # The tab is rendered inside st.tabs(...), so we just assert the
    # containing page loaded. Streamlit's testing framework doesn't
    # expose per-tab rendering, but any error in the tab body would
    # bubble up as result.exception.
    assert any("📦 Devcontainer" in tab.label for tab in result.tabs)


def test_devcontainer_api_endpoint_direct():
    """Hit the API the UI calls. Best coverage of the devcontainer engine."""
    resp = httpx.get(f"{API_BASE}/v1/export/{TEST_SANDBOX_ID}/devcontainer", timeout=30)
    assert resp.status_code == 200
    bundle = resp.json()
    assert "devcontainer.json" in bundle
    assert "docker-compose.yml" in bundle
    services = bundle["docker-compose.yml"]["services"]
    assert "workspace" in services
    # Sandbox has redis + pg plugins, both should appear.
    assert "redis" in services
    assert "pg" in services


# ── Feature 2: Cost + Carbon ───────────────────────────────────────────

def test_cost_page_renders():
    at = _fresh_app()
    _route(at, "cost")
    result = _run_and_assert_clean(at)
    # Cost page emits three top-level metrics.
    assert len(result.metric) >= 3


def test_cost_api_fleet():
    resp = httpx.get(f"{API_BASE}/v1/monitoring/cost", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert "sandboxes" in data
    assert "total_usd" in data
    assert "total_co2_g" in data


def test_cost_api_single_sandbox():
    resp = httpx.get(f"{API_BASE}/v1/monitoring/cost/{TEST_SANDBOX_ID}", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data["sandbox_id"] == TEST_SANDBOX_ID
    assert "usd" in data and "co2_g" in data


# ── Feature 3: Chaos toolkit ──────────────────────────────────────────

def test_chaos_tab_renders_without_error():
    at = _fresh_app()
    _route(at, "sandbox_detail", TEST_SANDBOX_ID)
    result = _run_and_assert_clean(at)
    assert any("🎭 Chaos" in t.label for t in result.tabs)


def test_chaos_cpu_throttle_and_reset_end_to_end():
    """Throttle CPU on the real redis container and verify reset undoes it.

    Uses `docker update --cpu-quota` rather than `docker pause` because
    some kernels (including the one this test suite runs on) don't have
    the cgroup freezer enabled — pause/unpause would hit the env-limit
    and return 500 even though the chaos engine is correct.
    """
    base = f"{API_BASE}/v1/chaos/{TEST_SANDBOX_ID}"

    r = httpx.post(
        f"{base}/cpu-throttle",
        json={"plugin_name": "redis", "cpus": 0.5},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    assert r.json()["fault_type"] == "cpu_throttle"

    active = httpx.get(base, timeout=5).json()["injections"]
    assert any(i["fault_type"] == "cpu_throttle" for i in active)

    # Reset clears the throttle.
    r = httpx.post(f"{base}/reset", timeout=10)
    assert r.status_code == 200
    assert httpx.get(base, timeout=5).json()["injections"] == []


def _kernel_has_cgroup_freezer() -> bool:
    """Detect whether the running kernel can pause containers.

    The chaos pause path uses `docker pause` which requires the cgroup
    v1 freezer (or v2 cgroup.freeze). Some minimal / sandboxed kernels
    omit it, in which case pause always 500s regardless of plugin code.
    We probe the API first so we only XFAIL the test when it's
    genuinely unsupported.
    """
    try:
        # Ask the dockerd we're pointed at whether a trivial container
        # can be paused. Doing this once at import time caches the
        # result so every test run pays at most one probe.
        import docker as _docker
        client = _docker.from_env(timeout=5)
        c = client.containers.run(
            "alpine:latest",
            command=["sh", "-c", "sleep 3"],
            detach=True,
        )
        try:
            c.pause()
            c.unpause()
            return True
        except Exception:
            return False
        finally:
            try:
                c.stop(timeout=0)
                c.remove(force=True)
            except Exception:
                pass
    except Exception:
        return False


_HAS_FREEZER = _kernel_has_cgroup_freezer()


@pytest.mark.skipif(
    not _HAS_FREEZER,
    reason="kernel has no cgroup freezer (docker pause not supported)",
)
def test_chaos_pause_unpause_redis_end_to_end():
    """Pause the real redis container, verify it's paused, then unpause."""
    base = f"{API_BASE}/v1/chaos/{TEST_SANDBOX_ID}"

    r = httpx.post(f"{base}/pause", json={"plugin_name": "redis"}, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["fault_type"] == "pause"

    r = httpx.post(f"{base}/unpause", json={"plugin_name": "redis"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["removed"]


def test_chaos_reset_clears_all():
    httpx.post(f"{API_BASE}/v1/chaos/{TEST_SANDBOX_ID}/reset", timeout=10)
    active = httpx.get(f"{API_BASE}/v1/chaos/{TEST_SANDBOX_ID}", timeout=5).json()
    assert active["injections"] == []


# ── Feature 4: pyverify ───────────────────────────────────────────────

def test_pyverify_tab_renders():
    at = _fresh_app()
    _route(at, "sandbox_detail", TEST_SANDBOX_ID)
    result = _run_and_assert_clean(at)
    assert any("✅ pyverify" in t.label for t in result.tabs)


def test_pyverify_run_yaml_hits_real_sandbox():
    yaml_text = """\
name: "UI test contract"
scenarios:
  - name: "redis round-trip"
    steps:
      - tool: redis_set
        args:
          key: ui-test-pyverify
          value: ok
        expect_no_error: true
      - tool: redis_get
        args:
          key: ui-test-pyverify
        expect_contains: ok
"""
    resp = httpx.post(
        f"{API_BASE}/v1/pyverify/{TEST_SANDBOX_ID}/run-yaml",
        json={"yaml": yaml_text},
        timeout=30,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["total"] == 2
    assert data["passed"] == 2


# ── Feature 5: Recorder ───────────────────────────────────────────────

def test_recorder_tab_renders():
    at = _fresh_app()
    _route(at, "sandbox_detail", TEST_SANDBOX_ID)
    result = _run_and_assert_clean(at)
    assert any("⏺ Recorder" in t.label for t in result.tabs)


def test_recorder_start_record_stop_export_end_to_end():
    # Clean slate.
    httpx.delete(f"{API_BASE}/v1/recorder/{TEST_SANDBOX_ID}", timeout=5)

    # Start.
    r = httpx.post(
        f"{API_BASE}/v1/recorder/{TEST_SANDBOX_ID}/start",
        json={"name": "ui-test-session"},
        timeout=5,
    )
    assert r.status_code == 200
    assert r.json()["active"] is True

    # Drive a real tool call while recording.
    r = httpx.post(
        f"{API_BASE}/v1/sandboxes/{TEST_SANDBOX_ID}/agent/tools/redis_set/execute",
        json={"params": {"key": "rec-check", "value": "1"}},
        timeout=10,
    )
    assert r.status_code == 200

    # Stop.
    r = httpx.post(f"{API_BASE}/v1/recorder/{TEST_SANDBOX_ID}/stop", timeout=5)
    assert r.status_code == 200
    assert r.json()["call_count"] >= 1

    # Export as pyverify spec.
    r = httpx.get(
        f"{API_BASE}/v1/recorder/{TEST_SANDBOX_ID}/export/pyverify", timeout=5,
    )
    assert r.status_code == 200
    spec = r.json()
    assert spec["name"] == "ui-test-session"
    assert len(spec["scenarios"][0]["steps"]) >= 1

    # Export as markdown.
    r = httpx.get(
        f"{API_BASE}/v1/recorder/{TEST_SANDBOX_ID}/export/markdown", timeout=5,
    )
    assert r.status_code == 200
    assert "# ui-test-session" in r.text

    # Discard for the next run.
    httpx.delete(f"{API_BASE}/v1/recorder/{TEST_SANDBOX_ID}", timeout=5)


# ── Feature 6: Ephemeral (spin) ───────────────────────────────────────

def test_spin_page_renders():
    at = _fresh_app()
    _route(at, "spin")
    _run_and_assert_clean(at)


def test_spin_presets_api():
    r = httpx.get(f"{API_BASE}/v1/spin/presets", timeout=5)
    assert r.status_code == 200
    presets = r.json()["presets"]
    assert "microservices" in presets


# Spin end-to-end creates a full sandbox which we don't want to pile up
# during test runs. Skip unless explicitly requested.
@pytest.mark.skipif(
    os.getenv("UI_TEST_HEAVY") != "1",
    reason="set UI_TEST_HEAVY=1 to exercise the full spin-up path",
)
def test_spin_creates_real_sandbox():
    r = httpx.post(
        f"{API_BASE}/v1/spin",
        json={"plugins": ["redis"], "ttl_seconds": 120, "name": "ui-spin"},
        timeout=60,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["short_id"]
    httpx.delete(f"{API_BASE}/v1/sandboxes/{data['sandbox_id']}", timeout=30)


# ── Feature 7: Branch ─────────────────────────────────────────────────

def test_branch_tab_renders():
    at = _fresh_app()
    _route(at, "sandbox_detail", TEST_SANDBOX_ID)
    result = _run_and_assert_clean(at)
    assert any("🌿 Branch" in t.label for t in result.tabs)


@pytest.mark.skipif(
    os.getenv("UI_TEST_HEAVY") != "1",
    reason="set UI_TEST_HEAVY=1 to exercise real branching (slow)",
)
def test_branch_creates_new_sandbox():
    r = httpx.post(
        f"{API_BASE}/v1/sandboxes/{TEST_SANDBOX_ID}/branch",
        json={"new_name": "ui-branch", "copy_data": False},
        timeout=120,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["source_sandbox_id"] == TEST_SANDBOX_ID
    httpx.delete(f"{API_BASE}/v1/sandboxes/{data['id']}", timeout=30)


# ── Feature 8: Time-Travel ────────────────────────────────────────────

def test_time_travel_tab_renders():
    at = _fresh_app()
    _route(at, "sandbox_detail", TEST_SANDBOX_ID)
    result = _run_and_assert_clean(at)
    assert any("⏮ Time-Travel" in t.label for t in result.tabs)


def test_time_travel_capture_list_delete():
    base = f"{API_BASE}/v1/time-travel/{TEST_SANDBOX_ID}"

    r = httpx.post(f"{base}/capture", json={"label": "ui-test"}, timeout=60)
    assert r.status_code == 200
    snap_id = r.json()["id"]

    r = httpx.get(base, timeout=5)
    assert r.status_code == 200
    snapshots = r.json()["snapshots"]
    assert any(s["id"] == snap_id for s in snapshots)

    r = httpx.delete(f"{base}/{snap_id}", timeout=30)
    assert r.status_code == 200


# ── Feature 9: Fork-from-production ───────────────────────────────────

def test_fork_tab_renders():
    at = _fresh_app()
    _route(at, "sandbox_detail", TEST_SANDBOX_ID)
    result = _run_and_assert_clean(at)
    assert any("🧬 Fork" in t.label for t in result.tabs)


def test_fork_introspect_and_preview_end_to_end():
    # First give postgres a schema to introspect.
    create_sql = (
        "CREATE TABLE IF NOT EXISTS ui_fork_users "
        "(id serial PRIMARY KEY, email text, first_name text, age int);"
    )
    r = httpx.post(
        f"{API_BASE}/v1/sandboxes/{TEST_SANDBOX_ID}/agent/tools/sql_execute/execute",
        json={"params": {"statement": create_sql}},
        timeout=15,
    )
    assert r.status_code == 200

    # Introspect.
    r = httpx.post(
        f"{API_BASE}/v1/fork/{TEST_SANDBOX_ID}/introspect",
        json={"tables": ["ui_fork_users"]},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["tables"], "introspect must return at least one table"
    # PII detection: email + first_name should be flagged.
    users = plan["tables"][0]
    pii_cols = set(users["pii_columns"])
    assert "email" in pii_cols
    assert "first_name" in pii_cols

    # Preview statements.
    r = httpx.post(
        f"{API_BASE}/v1/fork/{TEST_SANDBOX_ID}/preview",
        json={"tables": plan["tables"], "rows_per_table": 3, "seed": 42},
        timeout=10,
    )
    assert r.status_code == 200
    preview = r.json()
    assert preview["tables"][0]["statement_count"] == 3
    stmts = preview["tables"][0]["statements"]
    # PII values must be synthetic.
    assert any("@example.com" in s for s in stmts)


# ── Feature 10: MCP ────────────────────────────────────────────────────

def test_mcp_tab_renders():
    at = _fresh_app()
    _route(at, "sandbox_detail", TEST_SANDBOX_ID)
    result = _run_and_assert_clean(at)
    assert any("🤖 MCP" in t.label for t in result.tabs)


def test_mcp_info_endpoint():
    r = httpx.get(f"{API_BASE}/v1/mcp/{TEST_SANDBOX_ID}/info", timeout=5)
    assert r.status_code == 200
    info = r.json()
    assert info["protocol_version"] == "2025-06-18"
    assert info["tool_count"] > 0


def test_mcp_jsonrpc_initialize_and_tools_list():
    r = httpx.post(
        f"{API_BASE}/v1/mcp/{TEST_SANDBOX_ID}",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["serverInfo"]["name"] == "pysandbox"

    r = httpx.post(
        f"{API_BASE}/v1/mcp/{TEST_SANDBOX_ID}",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        timeout=10,
    )
    body = r.json()
    tools = body["result"]["tools"]
    assert all("inputSchema" in t for t in tools)


def test_mcp_tool_call_real_redis_roundtrip():
    r = httpx.post(
        f"{API_BASE}/v1/mcp/{TEST_SANDBOX_ID}",
        json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {
                "name": "redis_set",
                "arguments": {"key": "mcp-ui-test", "value": "hello"},
            },
        },
        timeout=15,
    )
    body = r.json()
    assert body["result"]["isError"] is False

    r = httpx.post(
        f"{API_BASE}/v1/mcp/{TEST_SANDBOX_ID}",
        json={
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "redis_get", "arguments": {"key": "mcp-ui-test"}},
        },
        timeout=15,
    )
    body = r.json()
    assert "hello" in body["result"]["content"][0]["text"]


# ── General: router / nav / dashboard still works ─────────────────────

def test_dashboard_page_still_renders():
    at = _fresh_app()
    _route(at, "dashboard")
    _run_and_assert_clean(at)


def test_sandbox_detail_page_has_all_18_tabs():
    at = _fresh_app()
    _route(at, "sandbox_detail", TEST_SANDBOX_ID)
    result = _run_and_assert_clean(at)
    labels = [t.label for t in result.tabs]
    expected = [
        "🔌 Plugins", "▶️ Run Tool", "📊 Monitoring", "💻 Terminal",
        "📖 Quickstart", "📜 Timeline", "🔑 Environment", "🌐 DNS",
        "🛠️ Agent Tools", "⚙️ Settings",
        "🎭 Chaos", "✅ pyverify", "⏺ Recorder", "🌿 Branch",
        "⏮ Time-Travel", "🧬 Fork", "🤖 MCP", "📦 Devcontainer",
    ]
    for needle in expected:
        assert any(needle in l for l in labels), f"tab missing: {needle!r}"
