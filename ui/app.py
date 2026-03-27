"""PySandbox Dashboard — Streamlit UI for managing sandboxes and plugins."""

import time

import httpx
import streamlit as st

import os

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
    col_left, col_right = st.columns([2, 1])
    with col_left:
        st.markdown('<div class="section-header">Sandboxes</div>', unsafe_allow_html=True)
    with col_right:
        if st.button("➕ New Sandbox", use_container_width=True, type="primary"):
            st.session_state.page = "create_sandbox"
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
                elif status == "error":
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

    # Quick Access URLs for web-accessible plugins
    WEB_PLUGINS = {"jupyter", "grafana", "prometheus", "jaeger", "elasticsearch",
                   "localstack", "minio", "vault", "rabbitmq", "clickhouse"}
    web_links = []
    for p in plugins:
        hp = p.get("host_port")
        pid = p.get("plugin_id", "")
        if hp and pid in WEB_PLUGINS:
            url = f"http://localhost:{hp}"
            # Add token for Jupyter
            env_data = api("GET", f"/v1/sandboxes/{sandbox_id}/env")
            token = ""
            if env_data and env_data.get("env"):
                token = env_data["env"].get("JUPYTER_TOKEN", "")
            if pid == "jupyter" and token:
                display_url = f"{url}?token={token}"
            else:
                display_url = url
            web_links.append((p.get("plugin_name", pid), display_url, pid))

    if web_links:
        st.markdown('<div class="section-header">Quick Access</div>', unsafe_allow_html=True)
        link_cols = st.columns(len(web_links))
        for i, (name, url, pid) in enumerate(web_links):
            with link_cols[i]:
                st.markdown(f"""
                <a href="{url}" target="_blank" style="
                    display:block; text-align:center; padding:12px 16px;
                    background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color:white; border-radius:10px; text-decoration:none;
                    font-weight:700; font-size:0.9rem;
                    box-shadow: 0 4px 12px rgba(102,126,234,0.3);
                ">🔗 Open {name}</a>
                """, unsafe_allow_html=True)

    # Tabs
    tab_plugins, tab_run, tab_env, tab_dns, tab_tools = st.tabs([
        f"🔌 Plugins ({len(plugins)})", "▶️ Run Tool", "🔑 Environment", "🌐 DNS", "🛠️ Agent Tools"
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
                    port_html = ""
                    if host_port:
                        # Determine protocol for clickable URL
                        pid = p.get("plugin_id", "")
                        if pid in ("jupyter", "grafana", "prometheus", "jaeger", "elasticsearch",
                                   "localstack", "minio", "vault", "rabbitmq", "clickhouse"):
                            url = f"http://localhost:{host_port}"
                            port_html = f'&nbsp;|&nbsp; Access: <a href="{url}" target="_blank"><strong>{url}</strong></a>'
                        else:
                            port_html = f'&nbsp;|&nbsp; Host Port: <strong>{host_port}</strong>'
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
                            st.markdown(f"- **`{t['name']}`** — {t.get('description', '')}")
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
            "catalog": ("📦", "Plugin Catalog"),
            "create_sandbox": ("➕", "New Sandbox"),
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
    else:
        page_dashboard()


if __name__ == "__main__":
    main()
