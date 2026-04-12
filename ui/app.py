"""PySandbox Dashboard — Streamlit UI for managing sandboxes and plugins."""

import time

import httpx
import streamlit as st

import os

from features import (
    page_cost,
    page_spin,
    tab_branch,
    tab_chaos,
    tab_devcontainer,
    tab_fork,
    tab_mcp,
    tab_pyverify,
    tab_recorder,
    tab_time_travel,
)

API_BASE = os.getenv("API_BASE", "http://localhost:18080")


# ── API Client ──────────────────────────────────────────────────────────────

def api(method: str, path: str, **kwargs) -> dict | list | None:
    """Call PySandbox REST API. Returns parsed JSON or None on error."""
    try:
        with httpx.Client(base_url=API_BASE, timeout=30) as client:
            resp = client.request(method, path, **kwargs)
            if resp.status_code >= 400:
                st.toast(f"API error: {resp.status_code} — {resp.text}", icon="🚨")
                return None
            return resp.json()
    except httpx.ConnectError:
        return None
    except Exception as e:
        st.toast(f"Connection error: {e}", icon="🚨")
        return None


def api_healthy() -> bool:
    result = api("GET", "/health")
    return result is not None and result.get("status") == "ok"


# ── Shared Styles ───────────────────────────────────────────────────────────

def inject_css():
    st.markdown("""
    <style>
    /* Global */
    .block-container { max-width: 1200px; padding-top: 2rem; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #0f0f23 0%, #1a1a3e 100%); }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown li,
    [data-testid="stSidebar"] .stMarkdown h1,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3 { color: #e0e0ff !important; }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px; padding: 24px; color: white;
        box-shadow: 0 4px 15px rgba(102,126,234,0.3);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(102,126,234,0.4);
    }
    .metric-card.green { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); box-shadow: 0 4px 15px rgba(17,153,142,0.3); }
    .metric-card.orange { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); box-shadow: 0 4px 15px rgba(245,87,108,0.3); }
    .metric-card.blue { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); box-shadow: 0 4px 15px rgba(79,172,254,0.3); }
    .metric-value { font-size: 2.5rem; font-weight: 800; margin: 0; }
    .metric-label { font-size: 0.9rem; opacity: 0.9; margin: 0; text-transform: uppercase; letter-spacing: 1px; }

    /* Status badges */
    .badge {
        display: inline-block; padding: 4px 12px; border-radius: 20px;
        font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .badge-running { background: #d4edda; color: #155724; }
    .badge-paused { background: #fff3cd; color: #856404; }
    .badge-destroyed { background: #f8d7da; color: #721c24; }
    .badge-healthy { background: #d4edda; color: #155724; }
    .badge-unhealthy { background: #f8d7da; color: #721c24; }
    .badge-error { background: #f8d7da; color: #721c24; }
    .badge-creating { background: #cce5ff; color: #004085; }
    .badge-resuming { background: #cce5ff; color: #004085; }
    .badge-destroying { background: #fff3cd; color: #856404; }

    /* Sandbox cards */
    .sandbox-card {
        background: white; border-radius: 12px; padding: 20px;
        border: 1px solid #e9ecef; margin-bottom: 12px;
        transition: all 0.2s;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .sandbox-card:hover {
        border-color: #667eea; box-shadow: 0 4px 20px rgba(102,126,234,0.15);
    }
    .sandbox-name { font-size: 1.2rem; font-weight: 700; color: #1a1a3e; margin: 0 0 4px 0; }
    .sandbox-id { font-size: 0.75rem; color: #999; font-family: monospace; }
    .sandbox-meta { font-size: 0.85rem; color: #666; margin-top: 8px; }

    /* Plugin catalog cards */
    .plugin-card {
        background: white; border-radius: 12px; padding: 20px;
        border: 1px solid #e9ecef;
        transition: all 0.2s;
        height: 100%;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .plugin-card:hover { border-color: #667eea; box-shadow: 0 4px 20px rgba(102,126,234,0.15); }
    .plugin-name { font-size: 1.1rem; font-weight: 700; color: #1a1a3e; margin: 0; }
    .plugin-desc { font-size: 0.85rem; color: #666; margin-top: 6px; }
    .plugin-category {
        display: inline-block; padding: 2px 10px; border-radius: 12px;
        font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
        background: #eef2ff; color: #4f46e5; margin-top: 8px;
    }
    .cat-databases { background: #dbeafe; color: #1d4ed8; }
    .cat-messaging { background: #fef3c7; color: #92400e; }
    .cat-cloud { background: #e0e7ff; color: #3730a3; }
    .cat-runtime { background: #d1fae5; color: #065f46; }
    .cat-monitoring { background: #fce7f3; color: #9d174d; }

    /* Section headers */
    .section-header {
        font-size: 1.3rem; font-weight: 700; color: #1a1a3e;
        border-bottom: 3px solid #667eea; padding-bottom: 8px;
        margin-bottom: 20px;
    }

    /* Table styling */
    .env-table { width: 100%; border-collapse: collapse; }
    .env-table th { text-align: left; padding: 10px 12px; background: #f8f9fa; border-bottom: 2px solid #dee2e6; font-size: 0.85rem; text-transform: uppercase; color: #666; }
    .env-table td { padding: 10px 12px; border-bottom: 1px solid #f0f0f0; font-family: monospace; font-size: 0.85rem; }
    .env-table tr:hover td { background: #f8f9fa; }

    /* Tool cards */
    .tool-card {
        background: #f8f9fa; border-radius: 8px; padding: 14px;
        border-left: 4px solid #667eea; margin-bottom: 8px;
    }
    .tool-name { font-weight: 700; color: #1a1a3e; font-family: monospace; }
    .tool-desc { font-size: 0.85rem; color: #666; margin-top: 4px; }

    /* Empty state */
    .empty-state {
        text-align: center; padding: 60px 20px; color: #999;
    }
    .empty-icon { font-size: 3rem; margin-bottom: 12px; }
    .empty-text { font-size: 1.1rem; }

    /* Logo area */
    .logo-area {
        text-align: center; padding: 20px 0 30px 0;
        border-bottom: 1px solid rgba(255,255,255,0.1);
        margin-bottom: 20px;
    }
    .logo-title { font-size: 1.6rem; font-weight: 800; color: #fff; margin: 0; }
    .logo-sub { font-size: 0.8rem; color: rgba(255,255,255,0.6); margin: 4px 0 0 0; }

    /* Hide default streamlit header */
    header[data-testid="stHeader"] { background: transparent; }
    </style>
    """, unsafe_allow_html=True)


# ── Helpers ─────────────────────────────────────────────────────────────────

CATEGORY_ICONS = {
    "databases": "🗄️", "messaging": "📨", "cloud": "☁️",
    "runtime": "⚙️", "monitoring": "📊",
}

STATUS_ICONS = {
    "running": "🟢", "paused": "🟡", "destroyed": "🔴",
    "error": "🔴", "creating": "🔵", "resuming": "🔵", "destroying": "🟡",
    "healthy": "🟢", "unhealthy": "🔴",
}


def status_badge(status: str) -> str:
    css_class = f"badge-{status}"
    return f'<span class="badge {css_class}">{status}</span>'


def metric_card(value, label, color=""):
    css = f"metric-card {color}" if color else "metric-card"
    return f"""
    <div class="{css}">
        <p class="metric-value">{value}</p>
        <p class="metric-label">{label}</p>
    </div>"""


# ── Pages ───────────────────────────────────────────────────────────────────

def page_dashboard():
    """Overview dashboard with metrics and sandbox list."""
    st.markdown("## Dashboard")

    connected = api_healthy()

    # Fetch data
    sandboxes = []
    catalog_data = {"plugins": [], "total": 0}
    if connected:
        sb_data = api("GET", "/v1/sandboxes")
        if sb_data:
            sandboxes = sb_data.get("sandboxes", [])
        cat_data = api("GET", "/v1/catalog")
        if cat_data:
            catalog_data = cat_data

    running = sum(1 for s in sandboxes if s.get("status") == "running")
    errored = sum(1 for s in sandboxes if s.get("status") == "error")

    # Metrics row
    cols = st.columns(4)
    with cols[0]:
        st.markdown(metric_card(
            "✓ Online" if connected else "✗ Offline",
            "API Status",
            "green" if connected else "orange"
        ), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(metric_card(len(sandboxes), "Total Sandboxes", "blue"), unsafe_allow_html=True)
    with cols[2]:
        if errored:
            st.markdown(metric_card(f"{running} / {errored} err", "Running / Errors", "orange"), unsafe_allow_html=True)
        else:
            st.markdown(metric_card(running, "Running", "green"), unsafe_allow_html=True)
    with cols[3]:
        st.markdown(metric_card(catalog_data["total"], "Available Plugins"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if not connected:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">🔌</div>
            <div class="empty-text">Cannot reach PySandbox API at <code>{API_BASE}</code></div>
            <div style="color:#bbb; margin-top:8px;">Start the server with <code>uvicorn pysandbox.main:app --port 18080</code></div>
        </div>
        """, unsafe_allow_html=True)
        return

    # Quick actions
    col_left, col_r1, col_r2, col_r3 = st.columns([3, 1, 1, 1])
    with col_left:
        st.markdown('<div class="section-header">Sandboxes</div>', unsafe_allow_html=True)
    with col_r1:
        if st.button("➕ New Sandbox", use_container_width=True, type="primary"):
            st.session_state.page = "create_sandbox"
            st.rerun()
    with col_r2:
        if st.button("🚀 Templates", use_container_width=True):
            st.session_state.page = "templates"
            st.rerun()
    with col_r3:
        if st.button("📥 Import", use_container_width=True):
            st.session_state.page = "import"
            st.rerun()

    # Batch operations
    if sandboxes and len(sandboxes) > 1:
        running_ids = [s["id"] for s in sandboxes if s.get("status") == "running"]
        paused_ids = [s["id"] for s in sandboxes if s.get("status") == "paused"]
        with st.expander("⚡ Batch Operations"):
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                if running_ids and st.button(f"⏸️ Pause All ({len(running_ids)})", use_container_width=True):
                    api("POST", "/v1/batch/pause", json={"sandbox_ids": running_ids})
                    st.toast("Paused all running sandboxes", icon="⏸️")
                    time.sleep(0.5)
                    st.rerun()
            with bc2:
                if paused_ids and st.button(f"▶️ Resume All ({len(paused_ids)})", use_container_width=True):
                    api("POST", "/v1/batch/resume", json={"sandbox_ids": paused_ids})
                    st.toast("Resumed all paused sandboxes", icon="▶️")
                    time.sleep(0.5)
                    st.rerun()
            with bc3:
                all_ids = [s["id"] for s in sandboxes if s.get("status") != "destroyed"]
                if all_ids and st.button(f"🗑️ Destroy All ({len(all_ids)})", use_container_width=True):
                    api("POST", "/v1/batch/destroy", json={"sandbox_ids": all_ids})
                    st.toast("Destroyed all sandboxes", icon="🗑️")
                    time.sleep(0.5)
                    st.rerun()

    if not sandboxes:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">📦</div>
            <div class="empty-text">No sandboxes yet. Create your first one!</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # Sandbox list
    for sb in sandboxes:
        status = sb.get("status", "unknown")
        with st.container():
            c1, c2, c3 = st.columns([4, 2, 2])
            with c1:
                error_html = ""
                if status == "error" and sb.get("error"):
                    error_html = f'<p style="color:#dc3545;font-size:0.85rem;margin-top:8px;background:#fff5f5;padding:8px 12px;border-radius:6px;border-left:4px solid #dc3545;"><strong>Error:</strong> {sb["error"]}</p>'
                st.markdown(f"""
                <div class="sandbox-card">
                    <p class="sandbox-name">{STATUS_ICONS.get(status, '⚪')} {sb['name']}</p>
                    <p class="sandbox-id">{sb['id']}</p>
                    <p class="sandbox-meta">
                        {status_badge(status)}
                        &nbsp;&nbsp;🌐 <code>{sb.get('dns_zone', '—')}</code>
                    </p>
                    {error_html}
                </div>
                """, unsafe_allow_html=True)
            with c2:
                if st.button("View Details", key=f"view_{sb['id']}", use_container_width=True):
                    st.session_state.page = "sandbox_detail"
                    st.session_state.sandbox_id = sb["id"]
                    st.rerun()
            with c3:
                if status == "running":
                    if st.button("⏸️ Pause", key=f"pause_{sb['id']}", use_container_width=True):
                        api("POST", f"/v1/sandboxes/{sb['id']}/pause")
                        st.toast(f"Paused {sb['name']}", icon="⏸️")
                        time.sleep(0.5)
                        st.rerun()
                elif status == "paused":
                    if st.button("▶️ Resume", key=f"resume_{sb['id']}", use_container_width=True):
                        api("POST", f"/v1/sandboxes/{sb['id']}/resume")
                        st.toast(f"Resumed {sb['name']}", icon="▶️")
                        time.sleep(0.5)
                        st.rerun()
                elif status in ("error", "creating", "destroying"):
                    if st.button("🗑️ Destroy", key=f"destroy_{sb['id']}", use_container_width=True):
                        api("DELETE", f"/v1/sandboxes/{sb['id']}")
                        st.toast(f"Destroyed {sb['name']}", icon="🗑️")
                        time.sleep(0.5)
                        st.rerun()


def page_create_sandbox():
    """Create a new sandbox with optional plugins."""
    st.markdown("## Create New Sandbox")

    if st.button("← Back to Dashboard"):
        st.session_state.page = "dashboard"
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    with st.form("create_sandbox_form"):
        name = st.text_input("Sandbox Name", placeholder="my-sandbox", help="Lowercase, alphanumeric, hyphens allowed")
        owner = st.text_input("Owner ID", value="default")

        st.markdown("**Initial Plugins** _(optional)_")
        # Get catalog for plugin selection
        catalog = api("GET", "/v1/catalog")
        plugin_options = []
        if catalog:
            plugin_options = [p["id"] for p in catalog.get("plugins", [])]

        selected_plugins = st.multiselect(
            "Select plugins to pre-install",
            options=plugin_options,
            help="These plugins will be installed when the sandbox is created"
        )

        submitted = st.form_submit_button("🚀 Create Sandbox", type="primary", use_container_width=True)

        if submitted:
            if not name:
                st.error("Sandbox name is required")
            else:
                plugins = [{"plugin_id": pid, "name": pid, "expose": True} for pid in selected_plugins]
                result = api("POST", "/v1/sandboxes", json={
                    "name": name,
                    "owner_id": owner,
                    "plugins": plugins,
                })
                if result:
                    st.toast(f"Created sandbox '{name}'!", icon="🎉")
                    st.session_state.page = "sandbox_detail"
                    st.session_state.sandbox_id = result["sandbox"]["id"]
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Failed to create sandbox")


def page_sandbox_detail():
    """Detailed view of a single sandbox."""
    sandbox_id = st.session_state.get("sandbox_id")
    if not sandbox_id:
        st.session_state.page = "dashboard"
        st.rerun()
        return

    data = api("GET", f"/v1/sandboxes/{sandbox_id}")
    if not data:
        st.error("Sandbox not found")
        if st.button("← Back"):
            st.session_state.page = "dashboard"
            st.rerun()
        return

    sb = data["sandbox"]
    plugins = data.get("plugins", [])
    status = sb.get("status", "unknown")

    # Header
    col_back, col_title, col_actions = st.columns([1, 4, 3])
    with col_back:
        if st.button("← Back"):
            st.session_state.page = "dashboard"
            st.rerun()
    with col_title:
        st.markdown(f"## {STATUS_ICONS.get(status, '⚪')} {sb['name']}")
    with col_actions:
        a1, a2, a3 = st.columns(3)
        with a1:
            if status == "running" and st.button("⏸️ Pause", use_container_width=True):
                api("POST", f"/v1/sandboxes/{sandbox_id}/pause")
                st.toast("Paused", icon="⏸️")
                time.sleep(0.5)
                st.rerun()
            elif status == "paused" and st.button("▶️ Resume", use_container_width=True):
                api("POST", f"/v1/sandboxes/{sandbox_id}/resume")
                st.toast("Resumed", icon="▶️")
                time.sleep(0.5)
                st.rerun()
        with a2:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
        with a3:
            if status != "destroyed" and st.button("🗑️ Destroy", use_container_width=True, type="secondary"):
                st.session_state[f"confirm_destroy_{sandbox_id}"] = True

    # Destroy confirmation
    if st.session_state.get(f"confirm_destroy_{sandbox_id}"):
        st.warning(f"Are you sure you want to destroy **{sb['name']}**? This cannot be undone.")
        dc1, dc2, dc3 = st.columns([2, 1, 1])
        with dc2:
            if st.button("Cancel", use_container_width=True):
                st.session_state[f"confirm_destroy_{sandbox_id}"] = False
                st.rerun()
        with dc3:
            if st.button("Yes, Destroy", type="primary", use_container_width=True):
                api("DELETE", f"/v1/sandboxes/{sandbox_id}")
                st.toast(f"Destroyed {sb['name']}", icon="🗑️")
                st.session_state[f"confirm_destroy_{sandbox_id}"] = False
                st.session_state.page = "dashboard"
                time.sleep(0.5)
                st.rerun()

    # Info bar
    st.markdown(f"""
    <div class="sandbox-card">
        <table style="width:100%;">
            <tr>
                <td><strong>ID</strong><br><code style="font-size:0.8rem">{sb['id']}</code></td>
                <td><strong>Status</strong><br>{status_badge(status)}</td>
                <td><strong>Network</strong><br><code>{sb.get('docker_network', '—')}</code></td>
                <td><strong>DNS Zone</strong><br><code>{sb.get('dns_zone', '—')}</code></td>
                <td><strong>Plugins</strong><br><strong>{len(plugins)}</strong> installed</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

    # Error details banner
    if status == "error" and sb.get("error"):
        st.error(f"**Sandbox failed:** {sb['error']}")

    # Quick Access URLs for web-accessible plugins (all that have browser UIs)
    WEB_PLUGINS = {
        "jupyter", "grafana", "prometheus", "jaeger", "rabbitmq",
        "minio", "neo4j", "dremio", "spark", "clickhouse", "nessie",
        "elasticsearch", "vault", "nats",
    }
    # Map plugin_id -> which container port has the web UI
    # Explicit for ALL web plugins to avoid accidentally linking the wrong port
    WEB_UI_PORTS = {
        "jupyter": 8888,
        "grafana": 3000,
        "prometheus": 9090,
        "jaeger": 16686,     # UI on 16686, not collector on 14268
        "rabbitmq": 15672,   # Management UI on 15672, not AMQP on 5672
        "minio": 9001,       # Console UI on 9001, not S3 API on 9000
        "neo4j": 7474,       # Browser UI on 7474, not Bolt on 7687
        "dremio": 9047,
        "spark": 8080,       # Master UI on 8080
        "clickhouse": 8123,  # HTTP Play UI on 8123, not native on 9000
        "nessie": 19120,     # REST API (browsable)
        "elasticsearch": 9200,  # REST API (browsable: /_cat/, /_cluster/health)
        "vault": 8200,       # Web UI at /ui/
        "nats": 8222,        # Monitoring dashboard on 8222, not client on 4222
    }
    # Fetch env vars once (for credential display) — only when plugins are installed.
    env_data = api("GET", f"/v1/sandboxes/{sandbox_id}/env") if plugins else None
    env_vars = (env_data or {}).get("env", {})

    web_links = []  # (name, url, plugin_id, cred_hint)
    for p in plugins:
        pid = p.get("plugin_id", "")
        host_ports_map = p.get("host_ports", {})
        if pid in WEB_UI_PORTS and host_ports_map:
            hp = host_ports_map.get(str(WEB_UI_PORTS[pid])) or host_ports_map.get(WEB_UI_PORTS[pid])
        else:
            hp = p.get("host_port")
        if hp and pid in WEB_PLUGINS:
            url = f"http://localhost:{hp}"
            display_url = url
            cred_hint = ""  # shown below the link for plugins that need login

            # ── Per-plugin URL tweaks + credential hints ──
            if pid == "jupyter":
                token = env_vars.get("JUPYTER_TOKEN", "")
                if token and token != "***":
                    display_url = f"{url}?token={token}"
            elif pid == "vault":
                display_url = f"{url}/ui/"
                token = env_vars.get("VAULT_TOKEN", "")
                if token and token != "***":
                    cred_hint = f"Token: <code>{token}</code>"
            elif pid == "elasticsearch":
                display_url = f"{url}/_cat/"
            elif pid == "nats":
                display_url = f"{url}/varz"
            elif pid == "minio":
                ak = env_vars.get("MINIO_ACCESS_KEY", env_vars.get("AWS_ACCESS_KEY_ID", ""))
                sk = env_vars.get("MINIO_SECRET_KEY", env_vars.get("AWS_SECRET_ACCESS_KEY", ""))
                if ak and ak != "***":
                    cred_hint = f"User: <code>{ak}</code> / Pass: <code>{sk}</code>"
            elif pid == "rabbitmq":
                u = env_vars.get("RABBITMQ_USER", "")
                pw = env_vars.get("RABBITMQ_PASSWORD", "")
                if u and u != "***":
                    cred_hint = f"User: <code>{u}</code> / Pass: <code>{pw}</code>"
            elif pid == "dremio":
                u = env_vars.get("DREMIO_USER", "")
                pw = env_vars.get("DREMIO_PASSWORD", "")
                if u and u != "***":
                    cred_hint = f"User: <code>{u}</code> / Pass: <code>{pw}</code>"
            elif pid == "clickhouse":
                display_url = f"{url}/play"
            # grafana, neo4j, prometheus, jaeger, spark → no creds needed (auth disabled)

            web_links.append((p.get("plugin_name", pid), display_url, pid, cred_hint))

    if web_links:
        st.markdown('<div class="section-header">Quick Access — Open in Browser</div>', unsafe_allow_html=True)
        cols_per_row = min(4, len(web_links))
        for row_start in range(0, len(web_links), cols_per_row):
            row_items = web_links[row_start:row_start + cols_per_row]
            link_cols = st.columns(cols_per_row)
            for i, (name, url, pid, cred) in enumerate(row_items):
                with link_cols[i]:
                    cred_html = f'<div style="font-size:0.72rem; color:#aaa; margin-top:4px;">{cred}</div>' if cred else ""
                    st.markdown(f"""
                    <div style="text-align:center;">
                        <a href="{url}" target="_blank" style="
                            display:block; padding:12px 16px;
                            background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color:white; border-radius:10px; text-decoration:none;
                            font-weight:700; font-size:0.9rem;
                            box-shadow: 0 4px 12px rgba(102,126,234,0.3);
                        ">🔗 Open {name}</a>
                        {cred_html}
                    </div>
                    """, unsafe_allow_html=True)

    # ── Verify / Seed / Quickstart Action Bar ──
    if status == "running":
        st.markdown('<div class="section-header">Developer Tools</div>', unsafe_allow_html=True)
        dev_c1, dev_c2, dev_c3 = st.columns(3)
        with dev_c1:
            if st.button("✅ Verify Sandbox", use_container_width=True, help="Run smoke tests on all plugins"):
                with st.spinner("Running verification checks..."):
                    verify_result = api("POST", f"/v1/sandboxes/{sandbox_id}/verify")
                if verify_result:
                    st.session_state[f"verify_result_{sandbox_id}"] = verify_result
                    st.rerun()
        with dev_c2:
            if st.button("🌱 Seed Sample Data", use_container_width=True, help="Pre-load realistic data into all plugins"):
                with st.spinner("Seeding data..."):
                    seed_result = api("POST", f"/v1/sandboxes/{sandbox_id}/seed")
                if seed_result:
                    st.session_state[f"seed_result_{sandbox_id}"] = seed_result
                    st.rerun()
        with dev_c3:
            qs_data = api("GET", f"/v1/sandboxes/{sandbox_id}/quickstart")
            if qs_data and qs_data.get("available") and "steps" in qs_data:
                st.markdown(f"**📖 Quickstart available** — {qs_data.get('title', 'Guide')}")
            else:
                st.markdown("*No quickstart for this sandbox*")

        # Show verification results if available
        vr = st.session_state.get(f"verify_result_{sandbox_id}")
        if vr:
            if vr.get("success"):
                st.success(f"✅ All checks passed! ({vr['passed']}/{vr['total']} in {vr['duration_ms']}ms)")
            else:
                st.error(f"❌ {vr['failed']} of {vr['total']} checks failed ({vr['duration_ms']}ms)")
            with st.expander("Verification Details", expanded=not vr.get("success")):
                for step in vr.get("steps", []):
                    icon = "✅" if step["passed"] else "❌"
                    cat = f"[{step['category']}]" if step.get("category") == "cross-plugin" else ""
                    st.markdown(f"{icon} **{step['plugin']}** — {step['name']} {cat} *({step['duration_ms']}ms)*")
                    if not step["passed"]:
                        st.caption(f"  {step['message']}")
                        if step.get("output"):
                            st.code(step["output"][:300], language="text")
            if st.button("Clear Results", key="clear_verify"):
                del st.session_state[f"verify_result_{sandbox_id}"]
                st.rerun()

        # Show seed results if available
        sr = st.session_state.get(f"seed_result_{sandbox_id}")
        if sr:
            if sr.get("success"):
                total_rows = sum(s.get("rows_created", 0) for s in sr.get("steps", []))
                st.success(f"🌱 Seeding complete! {sr['succeeded']} steps, ~{total_rows} records created ({sr['duration_ms']}ms)")
            else:
                st.warning(f"🌱 Seeding partially failed: {sr['succeeded']} succeeded, {sr['failed']} failed")
            with st.expander("Seed Details", expanded=not sr.get("success")):
                for step in sr.get("steps", []):
                    icon = "✅" if step["success"] else "❌"
                    rows = f" ({step['rows_created']} rows)" if step.get("rows_created") else ""
                    st.markdown(f"{icon} **{step['plugin']}** — {step['name']}{rows}")
                    if not step["success"]:
                        st.caption(f"  {step['message']}")
            if st.button("Clear Results", key="clear_seed"):
                del st.session_state[f"seed_result_{sandbox_id}"]
                st.rerun()

    # Tabs — the first 10 are the original ones; the last 8 are new features
    # (chaos, pyverify, recorder, branch, time-travel, fork, mcp, devcontainer).
    (
        tab_plugins, tab_run, tab_monitor, tab_terminal,
        tab_quickstart, tab_timeline, tab_env, tab_dns, tab_tools, tab_settings,
        feat_chaos, feat_pyverify, feat_recorder, feat_branch,
        feat_timetravel, feat_fork, feat_mcp, feat_devc,
    ) = st.tabs([
        f"🔌 Plugins ({len(plugins)})", "▶️ Run Tool", "📊 Monitoring", "💻 Terminal",
        "📖 Quickstart", "📜 Timeline", "🔑 Environment", "🌐 DNS", "🛠️ Agent Tools", "⚙️ Settings",
        "🎭 Chaos", "✅ pyverify", "⏺ Recorder", "🌿 Branch",
        "⏮ Time-Travel", "🧬 Fork", "🤖 MCP", "📦 Devcontainer",
    ])

    # ── Plugins Tab ──
    with tab_plugins:
        if status == "running":
            with st.expander("➕ Install a new plugin", expanded=False):
                catalog = api("GET", "/v1/catalog")
                if catalog:
                    plugin_ids = [p["id"] for p in catalog.get("plugins", [])]
                    installed_ids = {p.get("plugin_id") for p in plugins}
                    available = [pid for pid in plugin_ids if pid not in installed_ids]

                    if available:
                        with st.form("install_plugin"):
                            sel = st.selectbox("Plugin", available)
                            pname = st.text_input("Instance name", value=sel, help="Unique name within this sandbox")
                            pver = st.text_input("Version", placeholder="latest", help="Leave blank for default")
                            expose = st.checkbox("Expose on host port", value=True, help="Make accessible from outside the sandbox network")

                            if st.form_submit_button("Install Plugin", type="primary", use_container_width=True):
                                body = {"plugin_id": sel, "name": pname, "expose": expose}
                                if pver:
                                    body["version"] = pver
                                result = api("POST", f"/v1/sandboxes/{sandbox_id}/plugins", json=body)
                                if result:
                                    st.toast(f"Installed {sel}!", icon="✅")
                                    time.sleep(0.5)
                                    st.rerun()
                    else:
                        st.info("All available plugins are already installed.")

        if not plugins:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-icon">🔌</div>
                <div class="empty-text">No plugins installed yet</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            for p in plugins:
                p_status = p.get("status", "unknown")
                cols = st.columns([3, 1, 1, 1])
                with cols[0]:
                    icon = CATEGORY_ICONS.get(p.get("category", ""), "📦")
                    host_port = p.get("host_port")
                    host_ports_map = p.get("host_ports", {})
                    port_html = ""
                    pid = p.get("plugin_id", "")
                    web_pids = WEB_PLUGINS
                    if host_ports_map and len(host_ports_map) > 1:
                        # Show all mapped ports with links for web-accessible ports
                        parts = []
                        for cport, hport in host_ports_map.items():
                            if pid in web_pids:
                                url = f"http://localhost:{hport}"
                                parts.append(f'<a href="{url}" target="_blank">{cport}→{hport}</a>')
                            else:
                                parts.append(f"{cport}→<code>localhost:{hport}</code>")
                        port_html = f'&nbsp;|&nbsp; Ports: <strong>{", ".join(parts)}</strong>'
                    elif host_port:
                        if pid in web_pids:
                            url = f"http://localhost:{host_port}"
                            port_html = f'&nbsp;|&nbsp; Access: <a href="{url}" target="_blank"><strong>{url}</strong></a>'
                        else:
                            port_html = f'&nbsp;|&nbsp; Connect: <code>localhost:{host_port}</code>'
                    st.markdown(f"""
                    <div class="tool-card">
                        <span class="tool-name">{icon} {p.get('plugin_name', p.get('name', '?'))}</span>
                        <span style="float:right">{status_badge(p_status)}</span>
                        <div class="tool-desc">
                            Plugin: <strong>{p.get('plugin_id', '?')}</strong>
                            &nbsp;|&nbsp; Container: <code>{p.get('container_id', '—')[:12]}</code>
                            {port_html}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with cols[1]:
                    pname = p.get("plugin_name", p.get("name", ""))
                    if st.button("🔄", key=f"restart_{pname}", help="Restart plugin"):
                        api("POST", f"/v1/sandboxes/{sandbox_id}/plugins/{pname}/restart")
                        st.toast(f"Restarted {pname}", icon="🔄")
                        time.sleep(0.5)
                        st.rerun()
                with cols[2]:
                    if st.button("🛠️", key=f"tools_{pname}", help="View tools"):
                        tools_data = api("GET", f"/v1/sandboxes/{sandbox_id}/plugins/{pname}/tools")
                        if tools_data:
                            st.session_state[f"show_tools_{pname}"] = tools_data.get("tools", [])
                with cols[3]:
                    if status != "destroyed":
                        if st.button("🗑️", key=f"rm_{pname}", help="Remove plugin"):
                            api("DELETE", f"/v1/sandboxes/{sandbox_id}/plugins/{pname}")
                            st.toast(f"Removed {pname}", icon="🗑️")
                            time.sleep(0.5)
                            st.rerun()

                # Show tools if expanded
                tool_key = f"show_tools_{p.get('plugin_name', p.get('name', ''))}"
                if st.session_state.get(tool_key):
                    with st.expander(f"Tools for {p.get('plugin_name', p.get('name', ''))}", expanded=True):
                        for t in st.session_state[tool_key]:
                            # The per-plugin tools endpoint returns a flat
                            # list of tool name strings, not dicts. The
                            # all-tools endpoint returns dicts with name +
                            # description. Handle both shapes.
                            if isinstance(t, dict):
                                st.markdown(f"- **`{t['name']}`** — {t.get('description', '')}")
                            else:
                                st.markdown(f"- **`{t}`**")
                        if st.button("Close", key=f"close_{tool_key}"):
                            del st.session_state[tool_key]
                            st.rerun()

    # ── Run Tool Tab ──
    with tab_run:
        st.markdown('<div class="section-header">Execute Plugin Tools</div>', unsafe_allow_html=True)

        if status != "running":
            st.warning("Sandbox must be running to execute tools.")
        elif not plugins:
            st.info("Install a plugin first to get tools you can execute.")
        else:
            # Fetch all available tools
            all_tools = api("GET", f"/v1/sandboxes/{sandbox_id}/agent/tools")
            tool_list = all_tools.get("tools", []) if all_tools else []

            if not tool_list:
                st.info("No tools available. Install plugins to add tools.")
            else:
                # Tool selector
                tool_names = [t["name"] for t in tool_list]
                tool_map = {t["name"]: t for t in tool_list}

                selected_tool = st.selectbox(
                    "Select a tool to execute",
                    options=tool_names,
                    help="Choose a tool provided by one of the installed plugins",
                )

                if selected_tool:
                    tool_info = tool_map[selected_tool]
                    st.markdown(f"""
                    <div class="tool-card">
                        <span class="tool-name">{selected_tool}</span>
                        <div class="tool-desc">{tool_info.get('description', 'No description')}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Build parameter form from tool schema
                    params = tool_info.get("parameters", {})
                    param_props = params.get("properties", {}) if isinstance(params, dict) else {}
                    required_params = params.get("required", []) if isinstance(params, dict) else []

                    with st.form(f"run_tool_{selected_tool}"):
                        st.markdown("**Parameters**")
                        param_values = {}

                        if param_props:
                            for pname, pschema in param_props.items():
                                ptype = pschema.get("type", "string")
                                pdesc = pschema.get("description", "")
                                req_marker = " *" if pname in required_params else ""
                                label = f"{pname}{req_marker}"

                                if ptype == "boolean":
                                    param_values[pname] = st.checkbox(label, help=pdesc)
                                elif ptype == "integer":
                                    param_values[pname] = st.number_input(
                                        label, step=1, value=pschema.get("default", 0), help=pdesc
                                    )
                                elif ptype == "number":
                                    param_values[pname] = st.number_input(
                                        label, value=float(pschema.get("default", 0.0)), help=pdesc
                                    )
                                else:
                                    default = pschema.get("default", "")
                                    # Use text_area for params that typically hold code or long text
                                    if any(kw in pname.lower() for kw in ("query", "code", "body", "script", "command", "sql", "message", "content", "data")):
                                        param_values[pname] = st.text_area(
                                            label, value=str(default) if default else "",
                                            height=120, help=pdesc,
                                        )
                                    else:
                                        param_values[pname] = st.text_input(
                                            label, value=str(default) if default else "", help=pdesc,
                                        )

                        else:
                            st.markdown("_This tool takes no parameters._")

                        col_run, col_json = st.columns([1, 1])
                        with col_run:
                            run_clicked = st.form_submit_button(
                                "▶️ Execute", type="primary", use_container_width=True
                            )
                        with col_json:
                            show_raw = st.form_submit_button(
                                "📋 Show as JSON", use_container_width=True
                            )

                        if run_clicked:
                            # Filter out empty optional params
                            cleaned = {}
                            for k, v in param_values.items():
                                if v != "" and v is not None:
                                    cleaned[k] = v

                            with st.spinner(f"Executing {selected_tool}..."):
                                result = api(
                                    "POST",
                                    f"/v1/sandboxes/{sandbox_id}/agent/tools/{selected_tool}/execute",
                                    json={"params": cleaned},
                                )

                            if result:
                                st.toast(f"Tool '{selected_tool}' executed!", icon="✅")
                                st.session_state[f"tool_result_{sandbox_id}"] = result
                            else:
                                st.error(f"Failed to execute '{selected_tool}'")

                        if show_raw:
                            cleaned = {k: v for k, v in param_values.items() if v != "" and v is not None}
                            st.code(
                                f"POST /v1/sandboxes/{sandbox_id}/agent/tools/{selected_tool}/execute\n"
                                + f'{{"params": {cleaned}}}',
                                language="json",
                            )

                # Show last result
                result_key = f"tool_result_{sandbox_id}"
                if st.session_state.get(result_key):
                    res = st.session_state[result_key]
                    st.markdown('<div class="section-header">Result</div>', unsafe_allow_html=True)
                    res_status = res.get("status", "unknown")
                    if res_status == "completed":
                        st.success(f"Status: {res_status}")
                    else:
                        st.error(f"Status: {res_status}")

                    result_data = res.get("result", res.get("error", "No output"))
                    if isinstance(result_data, dict) or isinstance(result_data, list):
                        st.json(result_data)
                    else:
                        st.code(str(result_data))

                    if st.button("Clear Result"):
                        del st.session_state[result_key]
                        st.rerun()

    # ── Environment Tab ──
    with tab_env:
        env_data = api("GET", f"/v1/sandboxes/{sandbox_id}/env")
        if env_data and env_data.get("env"):
            env = env_data["env"]
            rows = ""
            for k, v in sorted(env.items()):
                masked = "••••••••" if v == "***REDACTED***" else f"<code>{v}</code>"
                rows += f"<tr><td><strong>{k}</strong></td><td>{masked}</td></tr>"
            st.markdown(f"""
            <table class="env-table">
                <thead><tr><th>Variable</th><th>Value</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-icon">🔑</div>
                <div class="empty-text">No environment variables set</div>
            </div>
            """, unsafe_allow_html=True)

    # ── DNS Tab ──
    with tab_dns:
        dns_data = api("GET", f"/v1/sandboxes/{sandbox_id}/dns")
        if dns_data and dns_data.get("records"):
            records = dns_data["records"]
            rows = ""
            for name, ip in sorted(records.items()):
                rows += f"<tr><td><code>{name}</code></td><td><code>{ip}</code></td></tr>"
            st.markdown(f"""
            <table class="env-table">
                <thead><tr><th>DNS Name</th><th>IP Address</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-icon">🌐</div>
                <div class="empty-text">No DNS records yet</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Tools Tab ──
    with tab_tools:
        tools_data = api("GET", f"/v1/sandboxes/{sandbox_id}/agent/tools")
        if tools_data and tools_data.get("tools"):
            tools = tools_data["tools"]
            st.markdown(f"**{tools_data.get('total', len(tools))}** tools available")
            # Search
            search = st.text_input("🔍 Search tools", placeholder="Type to filter...")
            filtered = tools
            if search:
                filtered = [t for t in tools if search.lower() in t["name"].lower() or search.lower() in t.get("description", "").lower()]

            for t in filtered:
                st.markdown(f"""
                <div class="tool-card">
                    <span class="tool-name">{t['name']}</span>
                    <div class="tool-desc">{t.get('description', 'No description')}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-icon">🛠️</div>
                <div class="empty-text">No agent tools registered. Install plugins to add tools.</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Monitoring Tab ──
    with tab_monitor:
        st.markdown('<div class="section-header">Live Resource Monitoring</div>', unsafe_allow_html=True)
        if status != "running":
            st.warning("Sandbox must be running to view resource usage.")
        elif plugins:
            monitor_data = api("GET", f"/v1/monitoring/resources/{sandbox_id}")
            if monitor_data and monitor_data.get("stats"):
                for stat in monitor_data["stats"]:
                    pname = stat.get("plugin_name", "unknown")
                    cpu_pct = stat.get("cpu_percent", 0)
                    mem_used = stat.get("memory_usage_mb", 0)
                    mem_limit = stat.get("memory_limit_mb", 0)
                    mem_pct = stat.get("memory_percent", 0)
                    net_rx = stat.get("network_rx_mb", 0)
                    net_tx = stat.get("network_tx_mb", 0)
                    st.markdown(f"#### {pname}")
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    with mc1:
                        st.metric("CPU", f"{cpu_pct}%")
                    with mc2:
                        st.metric("Memory", f"{mem_used:.0f} / {mem_limit:.0f} MB")
                    with mc3:
                        st.metric("Mem %", f"{mem_pct:.1f}%")
                    with mc4:
                        st.metric("Network", f"↓{net_rx:.1f} ↑{net_tx:.1f} MB")
                    st.progress(min(cpu_pct / 100.0, 1.0))
            else:
                st.info("No monitoring data available. Containers may not be fully started.")

            # Health Dashboard
            st.markdown('<div class="section-header">Health Status</div>', unsafe_allow_html=True)
            health_data = api("GET", f"/v1/monitoring/health/{sandbox_id}")
            if health_data:
                hc1, hc2, hc3 = st.columns(3)
                with hc1:
                    st.markdown(metric_card(health_data["total"], "Total Plugins", "blue"), unsafe_allow_html=True)
                with hc2:
                    st.markdown(metric_card(health_data["healthy"], "Healthy", "green"), unsafe_allow_html=True)
                with hc3:
                    st.markdown(metric_card(health_data["unhealthy"], "Unhealthy", "orange"), unsafe_allow_html=True)

                for ph in health_data.get("plugins", []):
                    st.markdown(f"""
                    <div class="tool-card">
                        <span class="tool-name">{STATUS_ICONS.get(ph['status'], '⚪')} {ph['plugin_name']}</span>
                        <span style="float:right">{status_badge(ph['status'])}</span>
                        <div class="tool-desc">Version: {ph.get('version', '—')} | Since: {ph.get('installed_at', '—')[:19]}</div>
                    </div>
                    """, unsafe_allow_html=True)

            # Plugin logs
            st.markdown('<div class="section-header">Plugin Logs</div>', unsafe_allow_html=True)
            log_plugin = st.selectbox("Select plugin", [p.get("plugin_name", "") for p in plugins], key="log_plugin_sel")
            log_lines = st.slider("Lines", 10, 500, 50, key="log_lines_sl")
            if st.button("📋 Fetch Logs", key="fetch_logs_btn"):
                logs_data = api("GET", f"/v1/monitoring/logs/{sandbox_id}/{log_plugin}?tail={log_lines}")
                if logs_data:
                    st.code(logs_data.get("logs", "No logs"), language="text")

    # ── Terminal Tab ──
    with tab_terminal:
        st.markdown('<div class="section-header">Interactive Terminal</div>', unsafe_allow_html=True)
        if status != "running":
            st.warning("Sandbox must be running to use the terminal.")
        elif plugins:
            terminals_data = api("GET", f"/v1/terminal/{sandbox_id}")
            terminals = terminals_data.get("terminals", []) if terminals_data else []
            if terminals:
                term_plugin = st.selectbox(
                    "Select container",
                    [t["plugin_name"] for t in terminals],
                    key="term_plugin_sel"
                )
                cmd = st.text_input("Command", placeholder="ls -la /", key="term_cmd")
                if st.button("▶️ Execute", key="term_exec", type="primary"):
                    if cmd:
                        result = api("POST", f"/v1/terminal/{sandbox_id}/{term_plugin}", json={"command": cmd})
                        if result:
                            st.session_state["term_result"] = result

                if st.session_state.get("term_result"):
                    res = st.session_state["term_result"]
                    if res["status"] == "completed":
                        st.success(f"Executed: {res['command']}")
                    else:
                        st.error(f"Error: {res['command']}")
                    st.code(res.get("output", ""), language="text")
                    if st.button("Clear", key="term_clear"):
                        del st.session_state["term_result"]
                        st.rerun()

                # Command history / quick commands
                st.markdown("**Quick Commands:**")
                quick_cmds = ["ls -la /", "cat /etc/os-release", "ps aux", "df -h", "free -m", "env | sort"]
                qc_cols = st.columns(3)
                for qi, qcmd in enumerate(quick_cmds):
                    with qc_cols[qi % 3]:
                        if st.button(f"`{qcmd}`", key=f"qc_{qi}", use_container_width=True):
                            result = api("POST", f"/v1/terminal/{sandbox_id}/{term_plugin}", json={"command": qcmd})
                            if result:
                                st.session_state["term_result"] = result
                                st.rerun()
            else:
                st.info("No containers available for terminal access.")

    # ── Quickstart Tab ──
    with tab_quickstart:
        qs = api("GET", f"/v1/sandboxes/{sandbox_id}/quickstart")
        if qs and qs.get("available") and "steps" in qs:
            st.markdown(f'<div class="section-header">{qs["title"]}</div>', unsafe_allow_html=True)
            st.markdown(f'*{qs["description"]}*  —  **~{qs["estimated_minutes"]} min**')
            st.markdown("---")

            # Track completion state in session
            completed_key = f"qs_completed_{sandbox_id}"
            if completed_key not in st.session_state:
                st.session_state[completed_key] = set()

            for step in qs.get("steps", []):
                step_num = step["step"]
                is_done = step_num in st.session_state[completed_key]
                icon = "✅" if is_done else f"**{step_num}.**"

                st.markdown(f"{icon} **{step['title']}**")
                st.markdown(f"  {step['description']}")

                if step.get("tip"):
                    st.info(f"💡 {step['tip']}")

                # Show pre-filled command if there's a tool
                if step.get("tool"):
                    import json as _json
                    st.code(f"Tool: {step['tool']}\nParams: {_json.dumps(step['params'], indent=2)}", language="json")

                    if not is_done and status == "running":
                        if st.button(f"▶️ Run Step {step_num}", key=f"qs_run_{sandbox_id}_{step_num}", use_container_width=True):
                            with st.spinner(f"Running {step['title']}..."):
                                result = api("POST", f"/v1/sandboxes/{sandbox_id}/agent/tools/{step['tool']}/execute", json={"params": step["params"]})
                            if result:
                                st.session_state[completed_key].add(step_num)
                                if result.get("status") == "completed":
                                    st.success(f"Output: {str(result.get('result', ''))[:300]}")
                                else:
                                    st.error(f"Error: {result.get('error', 'Unknown')}")
                else:
                    st.markdown(f"  *Expected:* {step.get('expected_output', '')}")

                st.markdown("---")

            total = len(qs.get("steps", []))
            done = len(st.session_state[completed_key])
            if done == total and total > 0:
                st.balloons()
                st.success(f"🎉 Quickstart complete! All {total} steps finished.")
            else:
                st.progress(done / max(total, 1), text=f"{done}/{total} steps completed")

            if done > 0 and st.button("🔄 Reset Progress", key="qs_reset"):
                st.session_state[completed_key] = set()
                st.rerun()
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-icon">📖</div>
                <div class="empty-text">No quickstart guide available for this sandbox.</div>
                <div class="empty-subtext">Quickstarts are available for sandboxes created from templates.</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Timeline Tab ──
    with tab_timeline:
        st.markdown('<div class="section-header">Activity Timeline</div>', unsafe_allow_html=True)
        tl_data = api("GET", f"/v1/timeline/{sandbox_id}?limit=50")
        if tl_data and tl_data.get("entries"):
            st.markdown(f"**{tl_data['total']}** total events")
            for entry in tl_data["entries"]:
                sev = entry.get("severity", "info")
                sev_icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(sev, "ℹ️")
                ts = entry.get("timestamp", "")[:19].replace("T", " ")
                plugin_str = f" [{entry['plugin_name']}]" if entry.get("plugin_name") else ""
                st.markdown(f"""
                <div class="tool-card" style="border-left-color: {'#28a745' if sev=='success' else '#ffc107' if sev=='warning' else '#dc3545' if sev=='error' else '#667eea'}">
                    <span style="font-size:0.8rem; color:#999;">{sev_icon} {ts}{plugin_str}</span>
                    <div style="margin-top:4px;">{entry.get('description', '')}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-icon">📜</div>
                <div class="empty-text">No activity recorded yet</div>
            </div>
            """, unsafe_allow_html=True)

        # Add manual note
        with st.expander("Add a note"):
            note = st.text_input("Note", key="timeline_note")
            if st.button("📝 Add Note", key="add_note_btn"):
                if note:
                    api("POST", f"/v1/timeline/{sandbox_id}", json={
                        "event_type": "user.note",
                        "description": note,
                        "severity": "info",
                    })
                    st.toast("Note added!", icon="📝")
                    time.sleep(0.3)
                    st.rerun()

    # ── Settings Tab ──
    with tab_settings:
        st.markdown('<div class="section-header">Sandbox Settings</div>', unsafe_allow_html=True)

        # TTL Management
        st.markdown("#### ⏰ Time-to-Live (Auto-Destroy)")
        ttl_data = api("GET", f"/v1/ttl/{sandbox_id}")
        if ttl_data and ttl_data.get("active") and ttl_data.get("remaining_seconds") is not None:
            remaining = ttl_data["remaining_seconds"]
            hours = remaining // 3600
            mins = (remaining % 3600) // 60
            st.info(f"TTL active: **{hours}h {mins}m** remaining (expires at {ttl_data['expires_at'][:19]})")
            if st.button("🚫 Remove TTL (make permanent)", key="remove_ttl"):
                api("DELETE", f"/v1/ttl/{sandbox_id}")
                st.toast("TTL removed", icon="🚫")
                time.sleep(0.3)
                st.rerun()
        else:
            st.markdown("No TTL set — sandbox will run until manually destroyed.")
            ttl_hours = st.number_input("Set TTL (hours)", min_value=1, max_value=720, value=24, key="ttl_hours")
            if st.button("⏰ Set TTL", key="set_ttl", type="primary"):
                api("POST", f"/v1/ttl/{sandbox_id}", json={"ttl_seconds": ttl_hours * 3600})
                st.toast(f"TTL set to {ttl_hours} hours", icon="⏰")
                time.sleep(0.3)
                st.rerun()

        st.markdown("---")

        # Export
        st.markdown("#### 📤 Export Configuration")
        st.markdown("Export this sandbox's configuration as JSON to recreate it later.")
        if st.button("📤 Export Sandbox Config", key="export_btn"):
            export_data = api("GET", f"/v1/export/{sandbox_id}")
            if export_data:
                import json
                st.code(json.dumps(export_data, indent=2), language="json")
                st.download_button(
                    "💾 Download JSON",
                    json.dumps(export_data, indent=2),
                    file_name=f"sandbox-{sb['name']}-export.json",
                    mime="application/json",
                    key="download_export",
                )

    # ── New feature tabs ──
    # Each helper lives in features.py and takes the same shared api()
    # callable so the main app routing logic stays tiny.
    with feat_chaos:
        tab_chaos(api, sandbox_id, plugins)
    with feat_pyverify:
        tab_pyverify(api, sandbox_id)
    with feat_recorder:
        tab_recorder(api, sandbox_id)
    with feat_branch:
        tab_branch(api, sandbox_id)
    with feat_timetravel:
        tab_time_travel(api, sandbox_id)
    with feat_fork:
        tab_fork(api, sandbox_id)
    with feat_mcp:
        tab_mcp(api, sandbox_id)
    with feat_devc:
        tab_devcontainer(api, sandbox_id)


def page_catalog():
    """Browse all available plugins."""
    st.markdown("## Plugin Catalog")
    st.markdown("Browse all available plugins and their capabilities.")

    catalog = api("GET", "/v1/catalog")
    if not catalog:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">🔌</div>
            <div class="empty-text">Cannot load catalog. Is the API running?</div>
        </div>
        """, unsafe_allow_html=True)
        return

    plugins = catalog.get("plugins", [])

    # Category filter
    categories = sorted(set(p.get("category", "other") for p in plugins))
    col_search, col_filter = st.columns([2, 1])
    with col_search:
        search = st.text_input("🔍 Search plugins", placeholder="postgres, redis, kafka...")
    with col_filter:
        cat_filter = st.selectbox("Category", ["All"] + categories)

    filtered = plugins
    if search:
        filtered = [p for p in filtered if search.lower() in p["id"].lower() or search.lower() in p.get("display_name", "").lower() or search.lower() in p.get("description", "").lower()]
    if cat_filter != "All":
        filtered = [p for p in filtered if p.get("category") == cat_filter]

    st.markdown(f"**{len(filtered)}** plugins found")
    st.markdown("<br>", unsafe_allow_html=True)

    # Grid of plugin cards
    for i in range(0, len(filtered), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(filtered):
                p = filtered[i + j]
                cat = p.get("category", "other")
                icon = CATEGORY_ICONS.get(cat, "📦")
                tags_html = ""
                for tag in p.get("tags", [])[:3]:
                    tags_html += f'<span style="display:inline-block;padding:2px 6px;background:#f0f0f0;border-radius:4px;font-size:0.7rem;margin-right:4px;">{tag}</span>'

                with col:
                    st.markdown(f"""
                    <div class="plugin-card">
                        <p class="plugin-name">{icon} {p.get('display_name', p['id'])}</p>
                        <span class="plugin-category cat-{cat}">{cat}</span>
                        <p class="plugin-desc">{p.get('description', 'No description')}</p>
                        <div style="margin-top:8px">{tags_html}</div>
                        <div style="margin-top:10px; font-size:0.8rem; color:#999;">
                            Version: <strong>{p.get('default_version', '—')}</strong>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    bc1, bc2 = st.columns(2)
                    with bc1:
                        if st.button("View Details", key=f"cat_detail_{p['id']}", use_container_width=True):
                            st.session_state.page = "plugin_detail"
                            st.session_state.plugin_detail_id = p["id"]
                            st.rerun()
                    with bc2:
                        if st.button("🚀 Quick Launch", key=f"launch_{p['id']}", use_container_width=True, type="primary"):
                            result = api("POST", "/v1/sandboxes", json={
                                "name": f"{p['id']}-sandbox",
                                "owner_id": "default",
                                "plugins": [{"plugin_id": p["id"], "name": p["id"], "expose": True}],
                            })
                            if result:
                                st.toast(f"Created sandbox with {p['id']}!", icon="🚀")
                                st.session_state.page = "sandbox_detail"
                                st.session_state.sandbox_id = result["sandbox"]["id"]
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.toast(f"Failed to launch {p['id']}", icon="🚨")


def page_plugin_detail():
    """Detailed view of a single plugin from catalog."""
    plugin_id = st.session_state.get("plugin_detail_id")
    if not plugin_id:
        st.session_state.page = "catalog"
        st.rerun()
        return

    if st.button("← Back to Catalog"):
        st.session_state.page = "catalog"
        st.rerun()

    detail = api("GET", f"/v1/catalog/{plugin_id}")
    if not detail:
        st.error(f"Plugin '{plugin_id}' not found")
        return

    p = detail
    cat = p.get("category", "other")
    icon = CATEGORY_ICONS.get(cat, "📦")

    st.markdown(f"## {icon} {p.get('display_name', plugin_id)}")
    st.markdown(f"> {p.get('description', '')}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Category:** `{cat}`")
    with col2:
        st.markdown(f"**Default Version:** `{p.get('default_version', '—')}`")
    with col3:
        versions = p.get("supported_versions", [])
        st.markdown(f"**Versions:** {', '.join(f'`{v}`' for v in versions) if versions else '—'}")

    if p.get("tags"):
        st.markdown("**Tags:** " + " ".join(f"`{t}`" for t in p["tags"]))

    # Resource requirements
    res = p.get("resources", {})
    if res:
        st.markdown('<div class="section-header">Resource Requirements</div>', unsafe_allow_html=True)
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.metric("CPU", res.get("cpu", "—"))
        with rc2:
            st.metric("Memory", res.get("memory", "—"))
        with rc3:
            st.metric("Disk", res.get("disk", "—"))

    # Health check
    hc = p.get("health_check", {})
    if hc:
        st.markdown('<div class="section-header">Health Check</div>', unsafe_allow_html=True)
        st.json(hc)

    # Config schema
    schema = api("GET", f"/v1/catalog/{plugin_id}/schema")
    if schema and schema.get("config_params"):
        st.markdown('<div class="section-header">Configuration Parameters</div>', unsafe_allow_html=True)
        for param in schema["config_params"]:
            req = "✅ Required" if param.get("required") else "Optional"
            default = f" (default: `{param.get('default')}`)" if param.get("default") is not None else ""
            st.markdown(f"- **`{param['name']}`** ({param.get('type', 'string')}) — {req}{default}")
            if param.get("description"):
                st.markdown(f"  _{param['description']}_")

    # Ports
    ports = p.get("ports", [])
    if ports:
        st.markdown('<div class="section-header">Ports</div>', unsafe_allow_html=True)
        for port in ports:
            st.markdown(f"- **{port.get('name', '?')}**: `{port.get('port', '?')}/{port.get('protocol', 'tcp')}`")


def page_containers():
    """Manage all pysandbox Docker containers."""
    st.markdown("## Docker Containers")
    st.markdown("View and manage all PySandbox-managed Docker containers running on your machine.")

    data = api("GET", "/v1/containers")
    if not data:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">🐳</div>
            <div class="empty-text">Cannot fetch containers. Is the API running?</div>
        </div>
        """, unsafe_allow_html=True)
        return

    containers = data.get("containers", [])

    if not containers:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">🐳</div>
            <div class="empty-text">No PySandbox containers running</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # Metrics
    total = len(containers)
    running = sum(1 for c in containers if c["status"] == "running")
    exited = sum(1 for c in containers if c["status"] == "exited")

    cols = st.columns(3)
    with cols[0]:
        st.markdown(metric_card(total, "Total Containers", "blue"), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(metric_card(running, "Running", "green"), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(metric_card(exited, "Stopped / Exited", "orange"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Select all / none
    col_sel, col_actions = st.columns([2, 1])
    with col_sel:
        select_all = st.checkbox("Select all", key="select_all_containers")

    # Container list with checkboxes
    selected_ids = []
    for c in containers:
        cid = c["id"]
        short_id = c.get("short_id", cid[:12])
        status = c["status"]
        status_icon = "🟢" if status == "running" else "🔴" if status == "exited" else "🟡"
        host_ports_map = c.get("host_ports", {})
        if host_ports_map:
            ports_str = ", ".join(f"{cp}→{hp}" for cp, hp in host_ports_map.items())
            port_info = f" | Ports: **{ports_str}**"
        elif c.get("host_port"):
            port_info = f" | Port: **{c['host_port']}**"
        else:
            port_info = ""

        col_check, col_info = st.columns([0.5, 5])
        with col_check:
            checked = st.checkbox("", key=f"ct_{cid}", value=select_all, label_visibility="collapsed")
            if checked:
                selected_ids.append(cid)
        with col_info:
            st.markdown(f"""
            <div class="tool-card">
                <span class="tool-name">{status_icon} {c['name']}</span>
                <div class="tool-desc">
                    Image: <code>{c['image']}</code>
                    &nbsp;|&nbsp; Status: <strong>{status}</strong>
                    &nbsp;|&nbsp; ID: <code>{short_id}</code>
                    {port_info}
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Action buttons
    col_destroy, col_refresh, col_spacer = st.columns([1, 1, 3])
    with col_destroy:
        if selected_ids:
            if st.button(
                f"🗑️ Remove {len(selected_ids)} container{'s' if len(selected_ids) > 1 else ''}",
                type="primary", use_container_width=True,
            ):
                st.session_state["confirm_remove_containers"] = selected_ids
        else:
            st.button("🗑️ Select containers to remove", disabled=True, use_container_width=True)
    with col_refresh:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    # Confirmation
    if st.session_state.get("confirm_remove_containers"):
        ids_to_remove = st.session_state["confirm_remove_containers"]
        st.warning(f"Are you sure you want to **force remove {len(ids_to_remove)} container(s)**? This cannot be undone.")
        cc1, cc2, cc3 = st.columns([2, 1, 1])
        with cc2:
            if st.button("Cancel", use_container_width=True):
                del st.session_state["confirm_remove_containers"]
                st.rerun()
        with cc3:
            if st.button("Yes, Remove", type="primary", use_container_width=True):
                result = api("POST", "/v1/containers/remove", json={"container_ids": ids_to_remove})
                if result:
                    count = result.get("count", 0)
                    st.toast(f"Removed {count} container(s)", icon="🗑️")
                del st.session_state["confirm_remove_containers"]
                time.sleep(0.5)
                st.rerun()

    # ── Docker Networks ──
    st.markdown("---")
    st.markdown("## Docker Networks")
    net_data = api("GET", "/v1/containers/networks")
    networks = net_data.get("networks", []) if net_data else []

    if networks:
        net_cols = st.columns(3)
        with net_cols[0]:
            st.markdown(metric_card(len(networks), "Total Networks", "blue"), unsafe_allow_html=True)
        with net_cols[1]:
            empty_nets = sum(1 for n in networks if n["containers"] == 0)
            st.markdown(metric_card(empty_nets, "Empty (orphaned)", "orange"), unsafe_allow_html=True)
        with net_cols[2]:
            active_nets = sum(1 for n in networks if n["containers"] > 0)
            st.markdown(metric_card(active_nets, "Active", "green"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        for n in networks:
            status_icon = "🟢" if n["containers"] > 0 else "🟡"
            st.markdown(f"""
            <div class="tool-card">
                <span class="tool-name">{status_icon} {n['name']}</span>
                <div class="tool-desc">
                    Sandbox: <code>{n['sandbox_id'][:12]}</code>
                    &nbsp;|&nbsp; Containers: <strong>{n['containers']}</strong>
                    &nbsp;|&nbsp; ID: <code>{n['short_id']}</code>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        btn_cols = st.columns([1, 1, 1, 2])
        with btn_cols[0]:
            if st.button("🧹 Prune Empty Networks", use_container_width=True):
                result = api("POST", "/v1/containers/networks/prune")
                if result:
                    st.toast(f"Pruned {result.get('count', 0)} empty network(s)", icon="🧹")
                    time.sleep(0.5)
                    st.rerun()
        with btn_cols[1]:
            if st.button("💣 Remove ALL Networks", use_container_width=True):
                st.session_state["confirm_remove_networks"] = True
        with btn_cols[2]:
            if st.button("🔥 Full Cleanup (All)", use_container_width=True, type="primary"):
                st.session_state["confirm_full_cleanup"] = True

        if st.session_state.get("confirm_remove_networks"):
            st.warning("This will **force disconnect containers** and remove ALL pysandbox networks.")
            rc1, rc2 = st.columns(2)
            with rc1:
                if st.button("Cancel##net", use_container_width=True):
                    del st.session_state["confirm_remove_networks"]
                    st.rerun()
            with rc2:
                if st.button("Yes, Remove All Networks", type="primary", use_container_width=True):
                    all_net_ids = [n["id"] for n in networks]
                    result = api("POST", "/v1/containers/networks/remove", json={"network_ids": all_net_ids})
                    if result:
                        st.toast(f"Removed {result.get('count', 0)} network(s)", icon="💣")
                    del st.session_state["confirm_remove_networks"]
                    time.sleep(0.5)
                    st.rerun()

        if st.session_state.get("confirm_full_cleanup"):
            st.error("**DANGER**: This removes ALL pysandbox containers AND networks. All sandboxes will be destroyed.")
            rc1, rc2 = st.columns(2)
            with rc1:
                if st.button("Cancel##full", use_container_width=True):
                    del st.session_state["confirm_full_cleanup"]
                    st.rerun()
            with rc2:
                if st.button("Yes, Destroy Everything", type="primary", use_container_width=True):
                    result = api("POST", "/v1/containers/cleanup")
                    if result:
                        st.toast(
                            f"Removed {result.get('containers_removed', 0)} containers, "
                            f"{result.get('networks_removed', 0)} networks",
                            icon="🔥",
                        )
                    del st.session_state["confirm_full_cleanup"]
                    time.sleep(0.5)
                    st.rerun()
    else:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">🌐</div>
            <div class="empty-text">No PySandbox networks found</div>
        </div>
        """, unsafe_allow_html=True)


def page_templates():
    """Browse and launch sandbox templates."""
    st.markdown("## Sandbox Templates")
    st.markdown("Launch pre-configured stacks with a single click.")

    data = api("GET", "/v1/templates")
    if not data:
        st.info("Cannot load templates. Is the API running?")
        return

    templates = data.get("templates", [])
    st.markdown(f"**{len(templates)}** templates available")
    st.markdown("<br>", unsafe_allow_html=True)

    for i in range(0, len(templates), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(templates):
                t = templates[i + j]
                plugins_str = ", ".join(t.get("plugins", []))
                with col:
                    st.markdown(f"""
                    <div class="plugin-card">
                        <p class="plugin-name">{t.get('icon', '📦')} {t['name']}</p>
                        <span class="plugin-category">{t.get('category', 'general')}</span>
                        <p class="plugin-desc">{t.get('description', '')}</p>
                        <div style="margin-top:8px; font-size:0.8rem; color:#999;">
                            Plugins: <strong>{t.get('plugin_count', 0)}</strong> ({plugins_str})
                            <br>Est. startup: ~{t.get('estimated_startup_seconds', 60)}s
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    name = st.text_input("Name", value=f"{t['id']}-sandbox", key=f"tpl_name_{t['id']}")
                    if st.button(f"🚀 Launch {t['name']}", key=f"launch_tpl_{t['id']}", type="primary", use_container_width=True):
                        result = api("POST", "/v1/templates/launch", json={
                            "name": name,
                            "template_id": t["id"],
                        })
                        if result:
                            st.toast(f"Launched {t['name']}!", icon="🚀")
                            st.session_state.page = "sandbox_detail"
                            st.session_state.sandbox_id = result["sandbox"]["id"]
                            time.sleep(0.5)
                            st.rerun()


def page_import():
    """Import a sandbox from JSON config."""
    st.markdown("## Import Sandbox")

    if st.button("← Back to Dashboard"):
        st.session_state.page = "dashboard"
        st.rerun()

    config_text = st.text_area("Paste exported sandbox JSON", height=300,
                               help="Paste the JSON from a sandbox export")
    name_override = st.text_input("Override name (optional)", placeholder="my-imported-sandbox")

    if st.button("📥 Import", type="primary", use_container_width=True):
        if not config_text:
            st.error("Please paste a config")
            return
        try:
            import json
            config = json.loads(config_text)
        except Exception:
            st.error("Invalid JSON")
            return

        body = {"config": config}
        if name_override:
            body["name_override"] = name_override

        result = api("POST", "/v1/export/import", json=body)
        if result:
            st.toast("Sandbox imported!", icon="📥")
            st.session_state.page = "sandbox_detail"
            st.session_state.sandbox_id = result["sandbox"]["id"]
            time.sleep(0.5)
            st.rerun()


# ── Main App ────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="PySandbox Dashboard",
        page_icon="🧊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_css()

    # Initialize state
    if "page" not in st.session_state:
        st.session_state.page = "dashboard"

    # Sidebar
    with st.sidebar:
        st.markdown("""
        <div class="logo-area">
            <p class="logo-title">🧊 PySandbox</p>
            <p class="logo-sub">Plugin-based Sandbox Runtime</p>
        </div>
        """, unsafe_allow_html=True)

        nav_items = {
            "dashboard": ("📊", "Dashboard"),
            "templates": ("🚀", "Templates"),
            "catalog": ("📦", "Plugin Catalog"),
            "create_sandbox": ("➕", "New Sandbox"),
            "spin": ("🔥", "Spin Ephemeral"),
            "containers": ("🐳", "Containers"),
            "cost": ("💰", "Cost & Carbon"),
        }

        for key, (icon, label) in nav_items.items():
            selected = st.session_state.page == key or (key == "dashboard" and st.session_state.page == "sandbox_detail")
            btn_type = "primary" if selected else "secondary"
            if st.button(f"{icon} {label}", key=f"nav_{key}", use_container_width=True, type=btn_type):
                st.session_state.page = key
                st.rerun()

        st.markdown("---")
        st.markdown("##### Quick Stats")
        healthy = api_healthy()
        st.markdown(f"API: {'🟢 Online' if healthy else '🔴 Offline'}")

        if healthy:
            sb_data = api("GET", "/v1/sandboxes")
            if sb_data:
                total = len(sb_data.get("sandboxes", []))
                running = sum(1 for s in sb_data.get("sandboxes", []) if s.get("status") == "running")
                st.markdown(f"Sandboxes: **{running}** / {total} running")

        st.markdown("---")
        st.markdown(
            '<p style="font-size:0.75rem; color:rgba(255,255,255,0.4); text-align:center;">PySandbox v1.0</p>',
            unsafe_allow_html=True,
        )

    # Router
    page = st.session_state.page
    if page == "dashboard":
        page_dashboard()
    elif page == "create_sandbox":
        page_create_sandbox()
    elif page == "sandbox_detail":
        page_sandbox_detail()
    elif page == "catalog":
        page_catalog()
    elif page == "plugin_detail":
        page_plugin_detail()
    elif page == "containers":
        page_containers()
    elif page == "templates":
        page_templates()
    elif page == "import":
        page_import()
    elif page == "spin":
        page_spin(api)
    elif page == "cost":
        page_cost(api)
    else:
        page_dashboard()


if __name__ == "__main__":
    main()
