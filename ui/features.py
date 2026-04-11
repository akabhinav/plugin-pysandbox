"""UI pages + sandbox-detail tabs for the 10 new engine features.

Split out of app.py to keep the main file focused on routing and the
pre-existing pages. Every function here takes an `api` callable so it
can be reused from tests or a future REST-less UI without pulling in
the full app module.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

import streamlit as st


API_FN = Callable[..., Any]  # signature: api(method, path, **kwargs) -> dict|list|None


# ══════════════════════════════════════════════════════════════════════
# Top-level pages (reachable from the sidebar)
# ══════════════════════════════════════════════════════════════════════


def page_cost(api: API_FN) -> None:
    """Fleet-wide cost + CO₂ dashboard."""
    st.markdown("## 💰 Cost & Carbon")
    st.caption(
        "Estimated USD spend and CO₂ footprint for every live sandbox, "
        "based on container CPU/memory stats. Rates default to AWS "
        "on-demand; savings tips surface idle-but-large sandboxes."
    )

    data = api("GET", "/v1/monitoring/cost")
    if not data:
        st.info("No cost data available. Is the API running?")
        return

    total_usd = data.get("total_usd", 0.0)
    total_co2_kg = data.get("total_co2_kg", 0.0)
    count = data.get("count", 0)

    m1, m2, m3 = st.columns(3)
    m1.metric("Active sandboxes", count)
    m2.metric("Total spend", f"${total_usd:,.2f}")
    m3.metric("CO₂ footprint", f"{total_co2_kg:.3f} kg")

    rows = data.get("sandboxes", [])
    if not rows:
        st.info("No running sandboxes yet.")
        return

    st.markdown("### Per-sandbox breakdown")
    for r in rows:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            c1.markdown(f"**{r.get('sandbox_name') or r['sandbox_id'][:8]}**")
            c1.caption(r["sandbox_id"])
            c2.metric("Age", f"{r['age_hours']:.1f}h")
            c3.metric("USD", f"${r['usd']:.3f}")
            c4.metric("CO₂", f"{r['co2_g']:.1f}g")
            if r.get("tip"):
                st.warning(f"💡 {r['tip']}")


def page_spin(api: API_FN) -> None:
    """Zero-config ephemeral sandbox launcher."""
    st.markdown("## 🚀 Spin Ephemeral Sandbox")
    st.caption(
        "Paste this page's URL into Slack / docs / an interview and "
        "a teammate gets a fresh sandbox in seconds. TTL defaults to "
        "30 min so abandoned sandboxes clean themselves up."
    )

    presets_data = api("GET", "/v1/spin/presets")
    preset_names = list((presets_data or {}).get("presets", {}).keys())

    col_a, col_b = st.columns([3, 1])
    with col_a:
        mode = st.radio(
            "Stack source",
            ["Preset", "Custom plugin list"],
            horizontal=True,
            label_visibility="collapsed",
        )

    if mode == "Preset":
        preset = st.selectbox(
            "Preset", preset_names or ["microservices"],
            help="Curated stacks optimized for fast one-off repros",
        )
        preset_plugins = (presets_data or {}).get("presets", {}).get(preset, [])
        if preset_plugins:
            st.caption(f"Includes: {', '.join(preset_plugins)}")
        stack_value = preset
        plugins_value: list[str] | None = None
    else:
        custom = st.text_input(
            "Plugins (comma-separated)",
            placeholder="postgres, redis, kafka",
        )
        stack_value = None
        plugins_value = [p.strip() for p in custom.split(",") if p.strip()]

    c1, c2 = st.columns(2)
    ttl_minutes = c1.slider("TTL (minutes)", 1, 60, 30)
    name = c2.text_input("Name (optional)", placeholder="bug-repro-for-issue-42")

    if st.button("🔥 Spin it up", type="primary", use_container_width=True):
        body = {
            "stack": stack_value,
            "plugins": plugins_value,
            "ttl_seconds": ttl_minutes * 60,
            "name": name or None,
        }
        result = api("POST", "/v1/spin", json=body)
        if result:
            st.success(f"Launched `{result['name']}` — expires in {ttl_minutes} minutes")
            st.code(
                f"short_id:   {result['short_id']}\n"
                f"sandbox_id: {result['sandbox_id']}\n"
                f"dns_zone:   {result.get('dns_zone', '')}",
                language="text",
            )
            if st.button("Open sandbox detail →", key="open_spin_result"):
                st.session_state.page = "sandbox_detail"
                st.session_state.sandbox_id = result["sandbox_id"]
                st.rerun()


# ══════════════════════════════════════════════════════════════════════
# Sandbox-detail tabs (reachable from page_sandbox_detail())
# ══════════════════════════════════════════════════════════════════════


def tab_chaos(api: API_FN, sandbox_id: str, plugins: list[dict]) -> None:
    """Inject and reset chaos effects on plugin containers."""
    st.markdown("#### 🎭 Chaos Engineering")
    st.caption(
        "Kill, pause, throttle, or add latency/loss to plugin containers "
        "to test your app's retry logic and circuit breakers. Every "
        "injection is tracked so `Reset` rolls the sandbox back cleanly."
    )

    plugin_names = [p.get("plugin_name") for p in plugins if p.get("plugin_name")]
    if not plugin_names:
        st.info("Install a plugin first.")
        return

    active = api("GET", f"/v1/chaos/{sandbox_id}")
    if active:
        injections = active.get("injections", [])
        if injections:
            st.markdown("**Active effects**")
            for inj in injections:
                st.markdown(
                    f"- `{inj['fault_type']}` on **{inj['plugin_name']}** "
                    f"({json.dumps(inj.get('params') or {})}) — since {inj['started_at'][:19]}"
                )
            if st.button("↩️ Reset all", key="chaos_reset", type="primary"):
                res = api("POST", f"/v1/chaos/{sandbox_id}/reset")
                if res is not None:
                    st.toast(f"Reset {res.get('reset_count', 0)} effects", icon="♻️")
                    time.sleep(0.3)
                    st.rerun()
        else:
            st.caption("_No active chaos effects._")

    st.divider()

    target = st.selectbox("Target plugin", plugin_names, key="chaos_target")
    action = st.selectbox(
        "Action",
        [
            "kill (SIGKILL container)",
            "pause (freeze processes)",
            "unpause",
            "latency (egress delay)",
            "packet loss",
            "cpu throttle",
            "memory throttle",
        ],
        key="chaos_action",
    )

    # Action-specific inputs
    with st.form("chaos_form"):
        if action.startswith("kill"):
            delay = st.slider("Delay (seconds)", 0, 60, 0)
            submit = st.form_submit_button("💀 Kill", type="primary", use_container_width=True)
            if submit:
                api("POST", f"/v1/chaos/{sandbox_id}/kill",
                    json={"plugin_name": target, "after_seconds": delay})
                st.toast(f"kill scheduled on {target}", icon="💀")
                time.sleep(0.3)
                st.rerun()

        elif action.startswith("pause"):
            if st.form_submit_button("⏸️ Pause", type="primary", use_container_width=True):
                api("POST", f"/v1/chaos/{sandbox_id}/pause", json={"plugin_name": target})
                st.toast(f"paused {target}", icon="⏸️")
                time.sleep(0.3)
                st.rerun()

        elif action.startswith("unpause"):
            if st.form_submit_button("▶️ Unpause", type="primary", use_container_width=True):
                api("POST", f"/v1/chaos/{sandbox_id}/unpause", json={"plugin_name": target})
                st.toast(f"unpaused {target}", icon="▶️")
                time.sleep(0.3)
                st.rerun()

        elif action.startswith("latency"):
            delay_ms = st.slider("Delay (ms)", 10, 2000, 200)
            jitter_ms = st.slider("Jitter (ms)", 0, 500, 0)
            if st.form_submit_button("🐌 Inject latency", type="primary", use_container_width=True):
                api("POST", f"/v1/chaos/{sandbox_id}/latency",
                    json={"plugin_name": target, "delay_ms": delay_ms, "jitter_ms": jitter_ms})
                st.toast(f"{delay_ms}ms latency on {target}", icon="🐌")
                time.sleep(0.3)
                st.rerun()

        elif action.startswith("packet loss"):
            loss = st.slider("Loss (%)", 1, 100, 5)
            if st.form_submit_button("📉 Drop packets", type="primary", use_container_width=True):
                api("POST", f"/v1/chaos/{sandbox_id}/loss",
                    json={"plugin_name": target, "loss_percent": float(loss)})
                st.toast(f"{loss}% loss on {target}", icon="📉")
                time.sleep(0.3)
                st.rerun()

        elif action.startswith("cpu"):
            cpus = st.slider("CPU (cores)", 0.1, 4.0, 0.5, step=0.1)
            if st.form_submit_button("🐢 Throttle CPU", type="primary", use_container_width=True):
                api("POST", f"/v1/chaos/{sandbox_id}/cpu-throttle",
                    json={"plugin_name": target, "cpus": cpus})
                st.toast(f"CPU throttled to {cpus} on {target}", icon="🐢")
                time.sleep(0.3)
                st.rerun()

        elif action.startswith("memory"):
            mem = st.slider("Memory (MB)", 64, 4096, 256)
            if st.form_submit_button("🧠 Throttle memory", type="primary", use_container_width=True):
                api("POST", f"/v1/chaos/{sandbox_id}/memory-throttle",
                    json={"plugin_name": target, "memory_mb": mem})
                st.toast(f"memory limited to {mem}MB on {target}", icon="🧠")
                time.sleep(0.3)
                st.rerun()


def tab_pyverify(api: API_FN, sandbox_id: str) -> None:
    """Run a declarative YAML/JSON verification spec against the sandbox."""
    st.markdown("#### ✅ pyverify — Declarative Contract")
    st.caption(
        "Run an integration contract expressed as a YAML spec. Replaces "
        "mock-heavy integration tests with real calls against the live "
        "stack in seconds."
    )

    default_yaml = """\
name: "Smoke contract"
scenarios:
  - name: "Sanity check"
    steps:
      - tool: sql_query
        args:
          query: "SELECT 1"
        expect_contains: "1"
"""
    yaml_text = st.text_area(
        "pyverify.yaml",
        value=st.session_state.get(f"pyv_{sandbox_id}", default_yaml),
        height=260,
    )
    st.session_state[f"pyv_{sandbox_id}"] = yaml_text

    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶️ Run", type="primary", use_container_width=True):
            result = api(
                "POST", f"/v1/pyverify/{sandbox_id}/run-yaml",
                json={"yaml": yaml_text},
            )
            if result:
                st.session_state[f"pyv_result_{sandbox_id}"] = result
    with c2:
        if st.button("🧹 Clear result", use_container_width=True):
            st.session_state.pop(f"pyv_result_{sandbox_id}", None)

    result = st.session_state.get(f"pyv_result_{sandbox_id}")
    if result:
        if result.get("success"):
            st.success(
                f"✅ {result.get('passed', 0)}/{result.get('total', 0)} passed "
                f"in {result.get('duration_ms', 0)}ms",
            )
        else:
            st.error(
                f"❌ {result.get('failed', 0)} failed "
                f"/ {result.get('passed', 0)} passed",
            )
        for step in result.get("steps", []):
            icon = "✓" if step["passed"] else "✗"
            with st.expander(
                f"{icon} {step['scenario']} › {step['name']}  ({step['duration_ms']}ms)",
                expanded=not step["passed"],
            ):
                st.markdown(f"**tool:** `{step['tool']}`  **message:** {step['message']}")
                if step.get("output"):
                    st.code(step["output"], language="text")
                if step.get("error"):
                    st.caption(f"error: {step['error']}")


def tab_recorder(api: API_FN, sandbox_id: str) -> None:
    """Start/stop a recording and export as pyverify spec or markdown."""
    st.markdown("#### ⏺ Sandbox Recorder")
    st.caption(
        "Capture every agent tool call you run on this sandbox, then "
        "export the session as a pyverify spec (to replay) or a markdown "
        "runbook (to paste into an incident report)."
    )

    existing = api("GET", f"/v1/recorder/{sandbox_id}")
    is_active = bool(existing and existing.get("active"))
    call_count = (existing or {}).get("call_count", 0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Status", "🔴 Recording" if is_active else "⚪ Idle")
    c2.metric("Captured calls", call_count)
    c3.metric("Session name", (existing or {}).get("name") or "—")

    colA, colB, colC = st.columns(3)
    with colA:
        name = st.text_input("Session name", placeholder="incident-42", key=f"rec_name_{sandbox_id}")
        if st.button("▶️ Start", use_container_width=True, disabled=is_active):
            api("POST", f"/v1/recorder/{sandbox_id}/start",
                json={"name": name or None})
            st.toast("recording started", icon="🔴")
            time.sleep(0.2)
            st.rerun()
    with colB:
        if st.button("⏹ Stop", use_container_width=True, disabled=not is_active):
            api("POST", f"/v1/recorder/{sandbox_id}/stop")
            st.toast("recording stopped", icon="⏹")
            time.sleep(0.2)
            st.rerun()
    with colC:
        if st.button("🗑 Discard", use_container_width=True, disabled=not existing):
            api("DELETE", f"/v1/recorder/{sandbox_id}")
            st.toast("recording discarded", icon="🗑")
            time.sleep(0.2)
            st.rerun()

    if existing and existing.get("calls"):
        note = st.text_input(
            "Annotate last call",
            placeholder="this step fixed the stale lock",
            key=f"rec_note_{sandbox_id}",
        )
        if st.button("📝 Attach note", disabled=not note):
            api("POST", f"/v1/recorder/{sandbox_id}/annotate", json={"note": note})
            st.toast("note attached", icon="📝")
            st.rerun()

    st.divider()
    st.markdown("**Export**")
    e1, e2 = st.columns(2)
    with e1:
        if st.button("📄 As pyverify spec", disabled=not existing, use_container_width=True):
            spec = api("GET", f"/v1/recorder/{sandbox_id}/export/pyverify")
            if spec:
                st.code(json.dumps(spec, indent=2), language="json")
    with e2:
        if st.button("📘 As markdown runbook", disabled=not existing, use_container_width=True):
            # The markdown endpoint returns text/markdown, so api() handles the
            # JSON decode failure gracefully by returning None — we fall back
            # to a raw httpx call via the shared client below.
            import httpx
            import os
            base = os.getenv("API_BASE", "http://localhost:18080")
            try:
                with httpx.Client(base_url=base, timeout=30) as client:
                    resp = client.get(f"/v1/recorder/{sandbox_id}/export/markdown")
                    if resp.status_code == 200:
                        st.markdown(resp.text)
                    else:
                        st.error(f"Export failed: {resp.status_code}")
            except Exception as e:
                st.error(f"Export failed: {e}")

    if existing and existing.get("calls"):
        with st.expander(f"📜 Captured calls ({call_count})", expanded=False):
            for i, call in enumerate(existing["calls"], 1):
                status_icon = "✓" if call["status"] == "ok" else "✗"
                st.markdown(f"**{i}. {status_icon} `{call['tool']}`** — {call.get('note') or ''}")
                st.caption(json.dumps(call.get("args") or {}))


def tab_branch(api: API_FN, sandbox_id: str) -> None:
    """Fork the current sandbox into a new one with copied volume state."""
    st.markdown("#### 🌿 Branch This Sandbox")
    st.caption(
        "Clone this sandbox into a new one that shares the same plugin "
        "shape and a copy of every plugin volume — great for A/B testing "
        "a migration without destroying the current state."
    )

    with st.form(f"branch_form_{sandbox_id}"):
        new_name = st.text_input("New sandbox name", placeholder="feature-x-variant")
        owner = st.text_input("Owner", value="default")
        copy_data = st.checkbox(
            "Copy volume data (pauses source briefly)", value=True,
        )
        tag_text = st.text_input("Extra tags (k=v, comma-separated)", placeholder="ticket=ENG-42")
        submit = st.form_submit_button("🌿 Create branch", type="primary", use_container_width=True)

    if submit:
        if not new_name:
            st.error("Name is required")
            return
        tags = {}
        for pair in (tag_text or "").split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                tags[k.strip()] = v.strip()
        result = api(
            "POST", f"/v1/sandboxes/{sandbox_id}/branch",
            json={
                "new_name": new_name,
                "owner_id": owner,
                "copy_data": copy_data,
                "tags": tags or None,
            },
        )
        if result:
            st.success(f"Branched `{new_name}` — {len(result.get('volumes_copied', []))} volumes copied")
            st.session_state.page = "sandbox_detail"
            st.session_state.sandbox_id = result["id"]
            time.sleep(0.5)
            st.rerun()


def tab_time_travel(api: API_FN, sandbox_id: str) -> None:
    """Capture, list, rewind, and auto-capture snapshots."""
    st.markdown("#### ⏮ Time-Travel Snapshots")
    st.caption(
        "Take point-in-time captures of every plugin volume. Rewind "
        "later to undo a bad migration / accidental DELETE / corrupted "
        "cache without re-seeding from scratch."
    )

    snaps_data = api("GET", f"/v1/time-travel/{sandbox_id}") or {}
    snaps = snaps_data.get("snapshots", [])

    with st.form(f"snap_form_{sandbox_id}"):
        label = st.text_input(
            "Label (optional)", placeholder="before-migration-0042",
        )
        if st.form_submit_button("📸 Take snapshot", type="primary", use_container_width=True):
            res = api("POST", f"/v1/time-travel/{sandbox_id}/capture", json={"label": label or None})
            if res:
                st.toast(f"snapshot {res['id']} captured", icon="📸")
                time.sleep(0.3)
                st.rerun()

    st.markdown("**Auto-capture**")
    c1, c2, c3 = st.columns(3)
    interval = c1.slider("Every (seconds)", 30, 1800, 300, step=30)
    if c2.button("▶️ Start auto", use_container_width=True):
        api("POST", f"/v1/time-travel/{sandbox_id}/auto/start",
            json={"interval_seconds": interval})
        st.toast(f"auto-capture every {interval}s", icon="▶️")
    if c3.button("⏹ Stop auto", use_container_width=True):
        api("POST", f"/v1/time-travel/{sandbox_id}/auto/stop")
        st.toast("auto-capture stopped", icon="⏹")

    st.divider()
    st.markdown(f"**Snapshots ({len(snaps)})**")
    if not snaps:
        st.info("No snapshots yet — take one above.")
        return
    for s in snaps:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            c1.markdown(f"**{s['id']}**  _{s.get('label') or ''}_")
            c1.caption(s["taken_at"])
            c2.metric("Volumes", s.get("volume_count", 0))
            if c3.button("⏪ Rewind", key=f"rw_{s['id']}", type="primary", use_container_width=True):
                res = api("POST", f"/v1/time-travel/{sandbox_id}/rewind/{s['id']}")
                if res:
                    st.toast(f"rewound to {s['id']}", icon="⏪")
                    time.sleep(0.4)
                    st.rerun()
            if c4.button("🗑 Delete", key=f"del_{s['id']}", use_container_width=True):
                api("DELETE", f"/v1/time-travel/{sandbox_id}/{s['id']}")
                st.toast(f"deleted {s['id']}", icon="🗑")
                time.sleep(0.3)
                st.rerun()


def tab_fork(api: API_FN, sandbox_id: str) -> None:
    """Fork-from-production: introspect schema + plan + preview + apply."""
    st.markdown("#### 🧬 Fork from Production (PII-safe)")
    st.caption(
        "Introspect a real schema, detect PII columns, generate "
        "deterministic synthetic data, and apply it to a target sandbox. "
        "Works through the existing `sql_query` / `sql_execute` agent tools."
    )

    tables_raw = st.text_input(
        "Source tables (comma-separated)",
        placeholder="users, orders, events",
        key=f"fork_tables_{sandbox_id}",
    )
    tables = [t.strip() for t in (tables_raw or "").split(",") if t.strip()]

    c1, c2 = st.columns(2)
    rows = c1.slider("Rows per table", 5, 1000, 50)
    seed = c2.number_input("Seed", value=42, step=1)

    if st.button("🔎 Introspect + plan", type="primary", use_container_width=True, disabled=not tables):
        res = api(
            "POST", f"/v1/fork/{sandbox_id}/introspect",
            json={"tables": tables},
        )
        if res:
            st.session_state[f"fork_plan_{sandbox_id}"] = {
                **res,
                "rows_per_table": rows,
                "seed": int(seed),
            }

    plan = st.session_state.get(f"fork_plan_{sandbox_id}")
    if plan:
        st.markdown("**Plan — PII detection**")
        any_pii = False
        for t in plan.get("tables", []):
            pii_cols = t.get("pii_columns") or []
            if pii_cols:
                any_pii = True
            with st.container(border=True):
                st.markdown(f"**{t['name']}** — {len(t.get('columns', []))} columns")
                if pii_cols:
                    st.warning(f"🔒 Detected PII: {', '.join(pii_cols)} — will be synthesized")
                else:
                    st.caption("no PII detected in this table")
        if not any_pii:
            st.info("No PII columns detected — all columns will be type-filled.")

        st.divider()
        st.markdown("**Apply**")
        target = st.text_input(
            "Target sandbox ID", value=sandbox_id,
            help="Usually a fresh sandbox you just created",
            key=f"fork_target_{sandbox_id}",
        )
        cA, cB = st.columns(2)
        if cA.button("👁 Preview statements", use_container_width=True):
            prev = api(
                "POST", f"/v1/fork/{sandbox_id}/preview",
                json={
                    "tables": plan["tables"],
                    "rows_per_table": rows,
                    "seed": int(seed),
                },
            )
            if prev:
                for t in prev.get("tables", []):
                    with st.expander(f"{t['name']} — {t['statement_count']} statements"):
                        st.code("\n".join(t["statements"][:5]), language="sql")
                        if t["statement_count"] > 5:
                            st.caption(f"… and {t['statement_count']-5} more")
        if cB.button("🚀 Apply to target", type="primary", use_container_width=True):
            res = api(
                "POST", "/v1/fork/apply",
                json={
                    "target_sandbox_id": target,
                    "plan": {
                        "tables": plan["tables"],
                        "rows_per_table": rows,
                        "seed": int(seed),
                    },
                },
            )
            if res:
                st.success(
                    f"Inserted {res.get('total_inserted', 0)} rows "
                    f"across {len(res.get('per_table', []))} tables"
                )


def tab_mcp(api: API_FN, sandbox_id: str) -> None:
    """Show MCP connection info + test a tools/list call from the browser."""
    st.markdown("#### 🤖 MCP Server")
    st.caption(
        "Expose this sandbox's agent tools over the Model Context Protocol "
        "so Claude Desktop / Cursor can call them directly. The surface "
        "lives at `/v1/mcp/{sandbox_id}`."
    )

    info = api("GET", f"/v1/mcp/{sandbox_id}/info")
    if not info:
        st.info("MCP endpoint not reachable.")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Protocol", info.get("protocol_version", "—"))
    m2.metric("Tool count", info.get("tool_count", 0))
    m3.metric("Endpoint", info.get("endpoint", "—"))

    import os
    base = os.getenv("API_BASE", "http://localhost:18080")
    endpoint = f"{base}/v1/mcp/{sandbox_id}"

    st.markdown("**Claude Desktop config snippet**")
    st.code(
        json.dumps(
            {
                "mcpServers": {
                    "pysandbox": {
                        "url": endpoint,
                        "description": f"pysandbox sandbox {sandbox_id[:8]}",
                    },
                },
            },
            indent=2,
        ),
        language="json",
    )

    st.markdown("**Try it: tools/list**")
    if st.button("📡 Send tools/list", use_container_width=True):
        result = api(
            "POST", f"/v1/mcp/{sandbox_id}",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        if result:
            st.code(json.dumps(result, indent=2)[:4000], language="json")

    with st.expander("🛠 Available tools", expanded=False):
        for t in info.get("tools", []):
            st.markdown(f"- **{t['name']}** — {t.get('description', '')}")


def tab_devcontainer(api: API_FN, sandbox_id: str) -> None:
    """Render the sandbox as a VS Code devcontainer bundle."""
    st.markdown("#### 📦 Devcontainer Export")
    st.caption(
        "Generate a `.devcontainer/` bundle a teammate can open in VS "
        "Code to get the same stack without installing pysandbox."
    )

    if st.button("🏗 Build bundle", type="primary", use_container_width=True):
        bundle = api("GET", f"/v1/export/{sandbox_id}/devcontainer")
        if bundle:
            st.session_state[f"devc_{sandbox_id}"] = bundle

    bundle = st.session_state.get(f"devc_{sandbox_id}")
    if not bundle:
        return

    st.markdown("##### `.devcontainer/devcontainer.json`")
    st.code(json.dumps(bundle["devcontainer.json"], indent=2), language="json")

    st.markdown("##### `.devcontainer/docker-compose.yml`")
    try:
        import yaml as _yaml
        compose_text = _yaml.safe_dump(bundle["docker-compose.yml"], sort_keys=False)
    except Exception:
        compose_text = json.dumps(bundle["docker-compose.yml"], indent=2)
    st.code(compose_text, language="yaml")

    st.info(
        "💡 Drop both files into `.devcontainer/` in your repo, then "
        "**Reopen in Container** in VS Code."
    )
