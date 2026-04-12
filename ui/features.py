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


# ── Feature 11: LocalStack Dashboard ──────────────────────────────────────


def _ls_terminal(api: API_FN, sandbox_id: str, cmd: str) -> dict | None:
    """Run a command inside the localstack container via the terminal API."""
    return api("POST", f"/v1/terminal/{sandbox_id}/localstack", json={"command": cmd})


def tab_localstack(api: API_FN, sandbox_id: str) -> None:
    """LocalStack AWS services dashboard — browse S3, SQS, SNS, DynamoDB,
    Kinesis, SSM, IAM, CloudWatch, EventBridge, StepFunctions, API Gateway,
    CloudFormation, Route53, Secrets Manager. All free community services."""

    st.markdown("#### ☁️ LocalStack — AWS Services Dashboard")

    # ── Health / Running Services ─────────────────────────────────────
    st.markdown("##### Running Services")
    health_raw = api(
        "POST",
        f"/v1/sandboxes/{sandbox_id}/agent/tools/s3_list_buckets/execute",
        json={"params": {}},
    )
    # Use terminal exec to hit the LocalStack health endpoint directly
    health = _ls_terminal(api, sandbox_id, "curl -sf http://localhost:4566/_localstack/health 2>/dev/null || echo '{}'")
    if health and health.get("output"):
        try:
            h = json.loads(health["output"])
            services = h.get("services", {})
            if services:
                cols = st.columns(4)
                for i, (svc, status) in enumerate(sorted(services.items())):
                    with cols[i % 4]:
                        icon = "🟢" if status in ("running", "available") else "🔴"
                        st.markdown(f"{icon} **{svc}**")
            else:
                st.info("No service status available")
        except (json.JSONDecodeError, TypeError):
            st.warning("Could not parse LocalStack health response")
    else:
        st.info("Could not reach LocalStack health endpoint")

    st.divider()

    # ── S3 Buckets ────────────────────────────────────────────────────
    st.markdown("##### 🪣 S3 Buckets")
    col_s3_1, col_s3_2 = st.columns([3, 1])
    with col_s3_2:
        new_bucket = st.text_input("New bucket name", placeholder="my-data", key="ls_new_bucket")
        if st.button("➕ Create Bucket", key="ls_create_bucket", use_container_width=True):
            if new_bucket:
                result = _ls_terminal(api, sandbox_id, f"awslocal s3 mb s3://{new_bucket} 2>&1")
                if result:
                    st.toast(f"Created bucket: {new_bucket}", icon="🪣")
                    time.sleep(0.3)
                    st.rerun()
    with col_s3_1:
        buckets_result = api(
            "POST",
            f"/v1/sandboxes/{sandbox_id}/agent/tools/s3_list_buckets/execute",
            json={"params": {}},
        )
        bucket_output = (buckets_result or {}).get("result", "")
        if bucket_output and bucket_output.strip():
            for line in bucket_output.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                # awslocal output: "2024-01-15 10:00:00 bucket-name" or just "bucket-name"
                parts = line.rsplit(None, 1)
                bname = parts[-1] if parts else line
                bc1, bc2, bc3 = st.columns([3, 1, 1])
                bc1.markdown(f"🪣 **{bname}**")
                if bc2.button("📂 List", key=f"ls_list_{bname}"):
                    objs = api(
                        "POST",
                        f"/v1/sandboxes/{sandbox_id}/agent/tools/s3_list/execute",
                        json={"params": {"bucket": bname}},
                    )
                    if objs:
                        st.code(objs.get("result", ""), language="text")
                if bc3.button("🗑️", key=f"ls_del_bucket_{bname}"):
                    _ls_terminal(api, sandbox_id, f"awslocal s3 rb s3://{bname} --force 2>&1")
                    st.toast(f"Deleted bucket: {bname}", icon="🗑️")
                    time.sleep(0.3)
                    st.rerun()
        else:
            st.caption("No buckets yet")

    st.divider()

    # ── SQS Queues ────────────────────────────────────────────────────
    st.markdown("##### 📬 SQS Queues")
    col_sqs_1, col_sqs_2 = st.columns([3, 1])
    with col_sqs_2:
        new_queue = st.text_input("New queue name", placeholder="my-queue", key="ls_new_queue")
        if st.button("➕ Create Queue", key="ls_create_queue", use_container_width=True):
            if new_queue:
                api(
                    "POST",
                    f"/v1/sandboxes/{sandbox_id}/agent/tools/sqs_create_queue/execute",
                    json={"params": {"queue_name": new_queue}},
                )
                st.toast(f"Created queue: {new_queue}", icon="📬")
                time.sleep(0.3)
                st.rerun()
    with col_sqs_1:
        queues_result = _ls_terminal(api, sandbox_id, "awslocal sqs list-queues --output text 2>/dev/null || echo ''")
        queue_output = (queues_result or {}).get("output", "").strip()
        if queue_output:
            for line in queue_output.splitlines():
                line = line.strip()
                if not line or line.startswith("QUEUE"):
                    continue
                # Extract queue name from URL or raw line
                qname = line.rsplit("/", 1)[-1] if "/" in line else line
                qc1, qc2, qc3 = st.columns([3, 1, 1])
                qc1.markdown(f"📬 **{qname}**")
                if qc2.button("📨 Send", key=f"ls_send_{qname}"):
                    st.session_state[f"ls_sqs_send_target"] = qname
                if qc3.button("🗑️", key=f"ls_del_queue_{qname}"):
                    _ls_terminal(api, sandbox_id, f"awslocal sqs delete-queue --queue-url http://localhost:4566/000000000000/{qname} 2>&1")
                    st.toast(f"Deleted queue: {qname}", icon="🗑️")
                    time.sleep(0.3)
                    st.rerun()
        else:
            st.caption("No queues yet")

    # SQS send form
    send_target = st.session_state.get("ls_sqs_send_target")
    if send_target:
        with st.form(f"sqs_send_form_{send_target}"):
            st.markdown(f"**Send message to {send_target}**")
            msg_body = st.text_area("Message body", key="ls_sqs_msg")
            if st.form_submit_button("📨 Send Message"):
                api(
                    "POST",
                    f"/v1/sandboxes/{sandbox_id}/agent/tools/sqs_send/execute",
                    json={"params": {"queue_name": send_target, "message": msg_body}},
                )
                st.toast("Message sent!", icon="📨")
                del st.session_state["ls_sqs_send_target"]
                st.rerun()

    st.divider()

    # ── SNS Topics ────────────────────────────────────────────────────
    st.markdown("##### 📢 SNS Topics")
    col_sns_1, col_sns_2 = st.columns([3, 1])
    with col_sns_2:
        new_topic = st.text_input("New topic name", placeholder="notifications", key="ls_new_topic")
        if st.button("➕ Create Topic", key="ls_create_topic", use_container_width=True):
            if new_topic:
                api(
                    "POST",
                    f"/v1/sandboxes/{sandbox_id}/agent/tools/sns_create_topic/execute",
                    json={"params": {"topic_name": new_topic}},
                )
                st.toast(f"Created topic: {new_topic}", icon="📢")
                time.sleep(0.3)
                st.rerun()
    with col_sns_1:
        topics_result = _ls_terminal(api, sandbox_id, "awslocal sns list-topics --output text 2>/dev/null || echo ''")
        topic_output = (topics_result or {}).get("output", "").strip()
        if topic_output:
            for line in topic_output.splitlines():
                line = line.strip()
                if not line or line.startswith("TOPICS"):
                    continue
                tname = line.rsplit(":", 1)[-1] if ":" in line else line
                st.markdown(f"📢 **{tname}**")
        else:
            st.caption("No topics yet")

    st.divider()

    # ── DynamoDB Tables ───────────────────────────────────────────────
    st.markdown("##### 🗃️ DynamoDB Tables")
    tables_result = _ls_terminal(api, sandbox_id, "awslocal dynamodb list-tables --output text 2>/dev/null || echo ''")
    table_output = (tables_result or {}).get("output", "").strip()
    if table_output:
        for line in table_output.splitlines():
            line = line.strip()
            if not line or line.startswith("TABLENAMES"):
                continue
            st.markdown(f"🗃️ **{line}**")
    else:
        st.caption("No tables yet")

    st.divider()

    # ── Secrets Manager ───────────────────────────────────────────────
    st.markdown("##### 🔐 Secrets Manager")
    col_sec_1, col_sec_2 = st.columns([3, 1])
    with col_sec_2:
        with st.form("ls_secret_form"):
            sec_name = st.text_input("Secret name", placeholder="db/password", key="ls_sec_name")
            sec_value = st.text_input("Secret value", type="password", key="ls_sec_val")
            if st.form_submit_button("🔐 Store Secret"):
                if sec_name and sec_value:
                    api(
                        "POST",
                        f"/v1/sandboxes/{sandbox_id}/agent/tools/secretsmanager_put/execute",
                        json={"params": {"name": sec_name, "value": sec_value}},
                    )
                    st.toast(f"Stored secret: {sec_name}", icon="🔐")
                    time.sleep(0.3)
                    st.rerun()
    with col_sec_1:
        secrets_result = _ls_terminal(api, sandbox_id, "awslocal secretsmanager list-secrets --output text 2>/dev/null || echo ''")
        sec_output = (secrets_result or {}).get("output", "").strip()
        if sec_output and "None" not in sec_output:
            for line in sec_output.splitlines():
                line = line.strip()
                if not line:
                    continue
                st.markdown(f"🔐 {line}")
        else:
            st.caption("No secrets stored yet")

    st.divider()

    # ── Kinesis Streams ───────────────────────────────────────────────
    st.markdown("##### 🌊 Kinesis Streams")
    kin_result = _ls_terminal(api, sandbox_id, "awslocal kinesis list-streams --output text 2>/dev/null || echo ''")
    kin_out = (kin_result or {}).get("output", "").strip()
    col_kin_1, col_kin_2 = st.columns([3, 1])
    with col_kin_2:
        new_stream = st.text_input("Stream name", placeholder="events-stream", key="ls_new_stream")
        if st.button("➕ Create Stream", key="ls_create_stream", use_container_width=True):
            if new_stream:
                _ls_terminal(api, sandbox_id, f"awslocal kinesis create-stream --stream-name {new_stream} --shard-count 1 2>&1")
                st.toast(f"Created stream: {new_stream}", icon="🌊")
                time.sleep(0.3)
                st.rerun()
    with col_kin_1:
        if kin_out:
            for line in kin_out.splitlines():
                line = line.strip()
                if line and not line.startswith("STREAM"):
                    st.markdown(f"🌊 **{line}**")
        else:
            st.caption("No streams yet")

    st.divider()

    # ── SSM Parameter Store ───────────────────────────────────────────
    st.markdown("##### 📋 SSM Parameter Store")
    col_ssm_1, col_ssm_2 = st.columns([3, 1])
    with col_ssm_2:
        with st.form("ls_ssm_form"):
            ssm_name = st.text_input("Parameter name", placeholder="/app/db-host", key="ls_ssm_name")
            ssm_val = st.text_input("Value", key="ls_ssm_val")
            if st.form_submit_button("📋 Store Parameter"):
                if ssm_name and ssm_val:
                    _ls_terminal(api, sandbox_id,
                        f"awslocal ssm put-parameter --name {ssm_name} --value '{ssm_val}' --type String --overwrite 2>&1")
                    st.toast(f"Stored: {ssm_name}", icon="📋")
                    time.sleep(0.3)
                    st.rerun()
    with col_ssm_1:
        ssm_result = _ls_terminal(api, sandbox_id, "awslocal ssm describe-parameters --output text 2>/dev/null || echo ''")
        ssm_out = (ssm_result or {}).get("output", "").strip()
        if ssm_out:
            for line in ssm_out.splitlines():
                line = line.strip()
                if line:
                    st.markdown(f"📋 {line}")
        else:
            st.caption("No parameters yet")

    st.divider()

    # ── IAM / CloudWatch / Other Services ─────────────────────────────
    st.markdown("##### 📊 Other AWS Services")
    svc_tabs = st.tabs(["👤 IAM", "📊 CloudWatch", "🔄 StepFunctions", "🌐 API Gateway", "📦 CloudFormation", "🗺️ Route53", "📡 EventBridge"])

    with svc_tabs[0]:  # IAM
        iam_result = _ls_terminal(api, sandbox_id, "awslocal iam list-users --output text 2>/dev/null || echo ''")
        iam_out = (iam_result or {}).get("output", "").strip()
        new_user = st.text_input("Create IAM user", placeholder="dev-user", key="ls_iam_user")
        if st.button("➕ Create User", key="ls_create_user"):
            if new_user:
                _ls_terminal(api, sandbox_id, f"awslocal iam create-user --user-name {new_user} 2>&1")
                st.toast(f"Created IAM user: {new_user}", icon="👤")
                time.sleep(0.3)
                st.rerun()
        if iam_out:
            st.code(iam_out, language="text")
        else:
            st.caption("No IAM users yet")

    with svc_tabs[1]:  # CloudWatch
        cw_result = _ls_terminal(api, sandbox_id, "awslocal cloudwatch list-metrics --output text 2>/dev/null | head -20 || echo ''")
        cw_out = (cw_result or {}).get("output", "").strip()
        if cw_out:
            st.code(cw_out, language="text")
        else:
            st.caption("No CloudWatch metrics yet")

    with svc_tabs[2]:  # StepFunctions
        sfn_result = _ls_terminal(api, sandbox_id, "awslocal stepfunctions list-state-machines --output text 2>/dev/null || echo ''")
        sfn_out = (sfn_result or {}).get("output", "").strip()
        if sfn_out:
            st.code(sfn_out, language="text")
        else:
            st.caption("No state machines yet")

    with svc_tabs[3]:  # API Gateway
        apigw_result = _ls_terminal(api, sandbox_id, "awslocal apigateway get-rest-apis --output text 2>/dev/null || echo ''")
        apigw_out = (apigw_result or {}).get("output", "").strip()
        if apigw_out:
            st.code(apigw_out, language="text")
        else:
            st.caption("No REST APIs yet")

    with svc_tabs[4]:  # CloudFormation
        cfn_result = _ls_terminal(api, sandbox_id, "awslocal cloudformation list-stacks --output text 2>/dev/null || echo ''")
        cfn_out = (cfn_result or {}).get("output", "").strip()
        if cfn_out:
            st.code(cfn_out, language="text")
        else:
            st.caption("No stacks yet")

    with svc_tabs[5]:  # Route53
        r53_result = _ls_terminal(api, sandbox_id, "awslocal route53 list-hosted-zones --output text 2>/dev/null || echo ''")
        r53_out = (r53_result or {}).get("output", "").strip()
        if r53_out:
            st.code(r53_out, language="text")
        else:
            st.caption("No hosted zones yet")

    with svc_tabs[6]:  # EventBridge
        eb_result = _ls_terminal(api, sandbox_id, "awslocal events list-rules --output text 2>/dev/null || echo ''")
        eb_out = (eb_result or {}).get("output", "").strip()
        if eb_out:
            st.code(eb_out, language="text")
        else:
            st.caption("No EventBridge rules yet")

    st.divider()

    # ── Quick AWS CLI ─────────────────────────────────────────────────
    st.markdown("##### 💻 AWS CLI (awslocal)")
    cmd = st.text_input(
        "Run any awslocal command",
        placeholder="awslocal s3 ls  |  awslocal sqs list-queues  |  awslocal lambda list-functions",
        key="ls_awscli",
    )
    if st.button("▶️ Run", key="ls_run_cmd", use_container_width=True):
        if cmd:
            result = _ls_terminal(api, sandbox_id, cmd)
            if result:
                st.code(result.get("output", ""), language="text")
