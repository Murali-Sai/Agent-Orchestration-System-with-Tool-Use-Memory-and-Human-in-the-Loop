"""Agent Orchestration System with Tool Use, Memory, and Human-in-the-Loop — UI."""
from __future__ import annotations
import os, time, json
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# Render's `fromService` env reference resolves to a bare hostname (no scheme),
# so normalise: add https:// when missing and drop any trailing slash.
API = os.getenv("API_URL", "http://localhost:8000").strip()
if API and not API.startswith(("http://", "https://")):
    API = "https://" + API
API = API.rstrip("/")

st.set_page_config(
    page_title="Agent Orchestration System",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auto-refresh while task is running ──────────────────────────────────
if st.session_state.get("active_task"):
    st_autorefresh(interval=3000, key="poll")

# ════════════════════════════════════════════════════════════════════════
# GLOBAL CSS
# ════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ── Base & typography ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.main .block-container { padding: 2rem 2.5rem 3rem; max-width: 1400px; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0d1117;
    border-right: 1px solid #21262d;
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 0.9rem;
    color: #8b949e;
    padding: 0.45rem 0.75rem;
    border-radius: 6px;
    transition: all 0.2s;
    cursor: pointer;
}
[data-testid="stSidebar"] .stRadio label:hover { color: #e6edf3; background: #161b22; }
[data-testid="stSidebar"] .stRadio [data-testid="stMarkdownContainer"] p { font-weight: 500; }

/* ── Cards ── */
.card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1rem;
    transition: border-color 0.2s;
}
.card:hover { border-color: #388bfd44; }
.card-accent { border-left: 3px solid #388bfd; }
.card-success { border-left: 3px solid #3fb950; }
.card-warning { border-left: 3px solid #d29922; }
.card-danger  { border-left: 3px solid #f85149; }
.card-purple  { border-left: 3px solid #bc8cff; }

/* ── Page header ── */
.page-header {
    background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
    border: 1px solid #21262d;
    border-radius: 14px;
    padding: 1.8rem 2rem;
    margin-bottom: 1.8rem;
}
.page-header h1 {
    font-size: 1.7rem;
    font-weight: 700;
    color: #e6edf3;
    margin: 0 0 0.3rem;
}
.page-header p { color: #8b949e; margin: 0; font-size: 0.95rem; }

/* ── Status badges ── */
.badge {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}
.badge-done     { background: #1f4a2e; color: #3fb950; border: 1px solid #3fb95044; }
.badge-running  { background: #1a2d4a; color: #388bfd; border: 1px solid #388bfd44; }
.badge-planning { background: #1a2d4a; color: #79c0ff; border: 1px solid #79c0ff44; }
.badge-failed   { background: #4a1e1e; color: #f85149; border: 1px solid #f8514944; }
.badge-escalated{ background: #4a3500; color: #d29922; border: 1px solid #d2992244; }
.badge-pending  { background: #2a2a2a; color: #8b949e; border: 1px solid #8b949e44; }

/* ── Metric cards ── */
.metric-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 1.1rem 1.3rem;
    text-align: center;
}
.metric-card .label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.4rem; }
.metric-card .value { font-size: 1.7rem; font-weight: 700; color: #e6edf3; font-family: 'JetBrains Mono', monospace; }
.metric-card .sub   { font-size: 0.75rem; color: #8b949e; margin-top: 0.2rem; }

/* ── Agent pipeline chips ── */
.pipeline { display: flex; gap: 0.6rem; flex-wrap: wrap; margin: 1rem 0; align-items: center; }
.agent-chip {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.45rem 1rem;
    border-radius: 8px;
    font-size: 0.82rem;
    font-weight: 600;
    border: 1px solid;
    position: relative;
}
.agent-chip.done     { background: #1f4a2e44; color: #3fb950; border-color: #3fb95044; }
.agent-chip.in_progress { background: #1a2d4a; color: #388bfd; border-color: #388bfd; animation: pulse 2s infinite; }
.agent-chip.pending  { background: #161b22; color: #484f58; border-color: #21262d; }
.agent-chip.failed   { background: #4a1e1e44; color: #f85149; border-color: #f8514944; }
.agent-chip .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.arrow { color: #484f58; font-size: 1rem; }

@keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 #388bfd44; }
    50%       { box-shadow: 0 0 0 5px #388bfd11; }
}

/* ── Timeline trace ── */
.timeline { position: relative; padding-left: 1.5rem; }
.timeline::before {
    content: '';
    position: absolute; left: 0.4rem; top: 0; bottom: 0;
    width: 2px; background: #21262d;
}
.timeline-event { position: relative; margin-bottom: 1rem; }
.timeline-dot {
    position: absolute; left: -1.15rem; top: 0.35rem;
    width: 10px; height: 10px; border-radius: 50%;
    border: 2px solid currentColor;
    background: #0d1117;
}
.timeline-content {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 0.8rem 1rem;
}
.timeline-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 0.3rem;
}
.timeline-agent { font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }
.timeline-time  { font-size: 0.72rem; color: #484f58; font-family: 'JetBrains Mono', monospace; }
.timeline-action { font-size: 0.85rem; color: #8b949e; }

/* Agent colours */
.c-supervisor { color: #388bfd; }
.c-research   { color: #3fb950; }
.c-analysis   { color: #d29922; }
.c-writing    { color: #bc8cff; }
.c-code       { color: #f78166; }
.c-reviewer   { color: #79c0ff; }
.c-system     { color: #484f58; }

/* ── HITL escalation card ── */
.hitl-card {
    background: #1c1510;
    border: 1px solid #d2992244;
    border-left: 4px solid #d29922;
    border-radius: 12px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.2rem;
}
.hitl-title { font-size: 1rem; font-weight: 700; color: #d29922; margin-bottom: 0.6rem; }
.hitl-meta  { font-size: 0.82rem; color: #8b949e; margin-bottom: 0.8rem; }

/* ── Buttons ── */
[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #388bfd, #1f6feb) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
}
[data-testid="baseButton-secondary"] {
    background: #21262d !important;
    border: 1px solid #30363d !important;
    color: #e6edf3 !important;
    border-radius: 8px !important;
}

/* ── Inputs ── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background: #0d1117 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
    color: #e6edf3 !important;
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #388bfd !important;
    box-shadow: 0 0 0 3px #388bfd22 !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #161b22;
    border: 1px solid #21262d !important;
    border-radius: 8px !important;
}

/* ── Divider ── */
hr { border-color: #21262d !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0d1117; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════

def badge(status: str) -> str:
    cls = {
        "done": "badge-done", "running": "badge-running", "planning": "badge-planning",
        "failed": "badge-failed", "escalated": "badge-escalated",
        "executing": "badge-running", "reviewing": "badge-running",
    }.get(status, "badge-pending")
    return f'<span class="badge {cls}">{status}</span>'


def metric_card(label: str, value: str, sub: str = "") -> str:
    return f"""
    <div class="metric-card">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        {f'<div class="sub">{sub}</div>' if sub else ''}
    </div>"""


AGENT_ICONS = {
    "supervisor": "🧠", "research": "🔍", "analysis": "📊",
    "writing": "✍️", "code": "💻", "reviewer": "🔎", "system": "⚙️",
}
AGENT_COLORS = {
    "supervisor": "c-supervisor", "research": "c-research", "analysis": "c-analysis",
    "writing": "c-writing", "code": "c-code", "reviewer": "c-reviewer", "system": "c-system",
}


def pipeline_html(plan: list) -> str:
    if not plan:
        return ""
    chips = []
    for i, st_task in enumerate(plan):
        status = st_task.get("status", "pending")
        icon = {"done": "✓", "in_progress": "●", "failed": "✗", "escalated": "⚠"}.get(status, "○")
        specialist = st_task.get("specialist", "agent")
        chips.append(
            f'<div class="agent-chip {status}">'
            f'<span class="dot"></span>'
            f'{AGENT_ICONS.get(specialist, "🤖")} {specialist.title()}'
            f'</div>'
        )
        if i < len(plan) - 1:
            chips.append('<span class="arrow">→</span>')
    return f'<div class="pipeline">{"".join(chips)}</div>'


def _api(path: str, method="GET", timeout=10, **kwargs):
    try:
        fn = getattr(requests, method.lower())
        return fn(f"{API}{path}", timeout=timeout, **kwargs).json()
    except Exception:
        return None


def _api_health():
    """Health check tolerant of free-tier cold starts: on idle hosts the API can
    take ~30-60s to wake. Fast first probe (warm case), then a longer one that
    waits out a cold start so the sidebar shows 'Online' instead of flashing red."""
    for t in (8, 30):
        h = _api("/health", timeout=t)
        if h:
            return h
    return None


# ════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="padding: 1rem 0 0.5rem; text-align:center;">
        <div style="font-size:2rem;">⚡</div>
        <div style="font-size:0.95rem; font-weight:700; color:#e6edf3; letter-spacing:0.02em; line-height:1.3;">Agent Orchestration System</div>
        <div style="font-size:0.65rem; color:#484f58; margin-top:3px;">Tool Use · Memory · Human-in-the-Loop</div>
    </div>
    <hr style="margin:0.8rem 0 1rem;">
    """, unsafe_allow_html=True)

    page = st.radio(
        "nav",
        ["⚡  Submit Task", "📋  Task Monitor", "🔔  HITL Queue", "🔭  Trace Explorer", "🧠  Memory & Tools", "📈  Analytics"],
        label_visibility="collapsed",
    )
    page = page.split("  ", 1)[1]  # strip icon prefix

    st.markdown("<hr style='margin:1rem 0;'>", unsafe_allow_html=True)

    health = _api_health()
    if health:
        active   = health.get("tasks_active", 0)
        sb_ok    = health.get("supabase", False)
        cel_ok   = health.get("celery", False)
        def _dot(ok): return "#3fb950" if ok else "#484f58"
        st.markdown(f"""
        <div style="font-size:0.8rem; padding:0 0.4rem;">
            <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem;">
                <span style="width:8px;height:8px;border-radius:50%;background:#3fb950;display:inline-block;"></span>
                <span style="color:#3fb950;font-weight:600;">API Online</span>
                <span style="color:#484f58;margin-left:auto;">{active} task(s)</span>
            </div>
            <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem;">
                <span style="width:8px;height:8px;border-radius:50%;background:{_dot(sb_ok)};display:inline-block;"></span>
                <span style="color:{_dot(sb_ok)};">Supabase {'✓' if sb_ok else 'Offline'}</span>
            </div>
            <div style="display:flex;align-items:center;gap:0.5rem;">
                <span style="width:8px;height:8px;border-radius:50%;background:{_dot(cel_ok)};display:inline-block;"></span>
                <span style="color:{_dot(cel_ok)};">Celery {'✓' if cel_ok else 'Offline'}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:0.5rem;font-size:0.8rem;padding:0 0.4rem;">
            <span style="width:8px;height:8px;border-radius:50%;background:#d29922;display:inline-block;"></span>
            <span style="color:#d29922;font-weight:600;">API waking up…</span>
        </div>
        <div style="font-size:0.68rem;color:#484f58;padding:0.3rem 0.4rem 0;">
            Free tier cold start (~30–60s). Refresh in a moment.
        </div>
        """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE: SUBMIT TASK
# ════════════════════════════════════════════════════════════════════════
if page == "Submit Task":
    st.markdown("""
    <div class="page-header">
        <h1>⚡ Submit a Task</h1>
        <p>Describe your goal. The Supervisor will decompose it, dispatch specialists, and synthesize the result.</p>
    </div>
    """, unsafe_allow_html=True)

    # Agent capability chips
    st.markdown("""
    <div style="display:flex;gap:0.6rem;flex-wrap:wrap;margin-bottom:1.5rem;">
        <span style="background:#1f3a2e44;color:#3fb950;border:1px solid #3fb95033;padding:0.3rem 0.8rem;border-radius:6px;font-size:0.8rem;font-weight:500;">🔍 Web Research</span>
        <span style="background:#1a2d4a44;color:#d29922;border:1px solid #d2992233;padding:0.3rem 0.8rem;border-radius:6px;font-size:0.8rem;font-weight:500;">📊 Data Analysis</span>
        <span style="background:#2d1a4a44;color:#bc8cff;border:1px solid #bc8cff33;padding:0.3rem 0.8rem;border-radius:6px;font-size:0.8rem;font-weight:500;">✍️ Writing</span>
        <span style="background:#4a1e1e44;color:#f78166;border:1px solid #f7816633;padding:0.3rem 0.8rem;border-radius:6px;font-size:0.8rem;font-weight:500;">💻 Code Execution</span>
        <span style="background:#1a2d4a44;color:#79c0ff;border:1px solid #79c0ff33;padding:0.3rem 0.8rem;border-radius:6px;font-size:0.8rem;font-weight:500;">🔎 Quality Review</span>
    </div>
    """, unsafe_allow_html=True)

    with st.form("task_form", clear_on_submit=False):
        request = st.text_area(
            "What do you want to accomplish?",
            height=130,
            placeholder="e.g. Research the top 5 AI startups of 2025, analyze their funding and tech stack, and write an investor brief.",
        )
        col_a, col_b = st.columns([3, 1])
        with col_a:
            user_id = st.text_input("User ID", value="demo_user", label_visibility="collapsed",
                                     placeholder="User ID")
        with col_b:
            submitted = st.form_submit_button("Run Task ⚡", type="primary", use_container_width=True)

    if submitted and request.strip():
        resp = _api("/tasks", method="POST", json={"request": request, "user_id": user_id})
        if resp:
            st.session_state["active_task"] = resp["task_id"]
            st.session_state["active_request"] = request
        else:
            st.error("Failed to submit task — is the API running?")

    # ── Live task panel ──────────────────────────────────────────────
    if st.session_state.get("active_task"):
        task_id = st.session_state["active_task"]
        s = _api(f"/tasks/{task_id}")
        if not s:
            st.warning("Could not reach API.")
        else:
            status = s.get("status", "unknown")
            completed = s.get("completed", 0)
            total = s.get("total", 0)
            tokens = s.get("total_tokens", 0)
            score = s.get("reviewer_score", 0)
            tool_calls = s.get("total_tool_calls", 0)

            st.markdown("<hr>", unsafe_allow_html=True)

            # Header row
            h1, h2 = st.columns([5, 1])
            with h1:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:1rem;">'
                    f'<span style="font-size:1.1rem;font-weight:700;color:#e6edf3;">Task <code style="background:#21262d;padding:0.15rem 0.5rem;border-radius:5px;font-size:0.85rem;">{task_id}</code></span>'
                    f'{badge(status)}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with h2:
                if st.button("✕ Clear", use_container_width=True):
                    st.session_state.pop("active_task", None)
                    st.session_state.pop("active_request", None)
                    st.rerun()

            # Metrics row
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.markdown(metric_card("Subtasks", f"{completed}/{total}"), unsafe_allow_html=True)
            c2.markdown(metric_card("Tokens", f"{tokens:,}"), unsafe_allow_html=True)
            c3.markdown(metric_card("Tool Calls", str(tool_calls)), unsafe_allow_html=True)
            c4.markdown(metric_card("Review Score", f"{score:.2f}" if score else "—"), unsafe_allow_html=True)
            c5.markdown(metric_card("Confidence", f"{s.get('plan_confidence', 0):.2f}"), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Progress bar
            if total > 0:
                pct = int((completed / total) * 100)
                st.markdown(f"""
                <div style="margin-bottom:0.5rem;">
                    <div style="display:flex;justify-content:space-between;font-size:0.8rem;color:#8b949e;margin-bottom:0.4rem;">
                        <span>Execution Progress</span><span>{pct}%</span>
                    </div>
                    <div style="background:#21262d;border-radius:8px;height:8px;overflow:hidden;">
                        <div style="background:linear-gradient(90deg,#388bfd,#bc8cff);height:100%;width:{pct}%;border-radius:8px;transition:width 0.5s;"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Agent pipeline
            plan = s.get("plan", [])
            if plan:
                st.markdown(pipeline_html(plan), unsafe_allow_html=True)

            # Subtask cards
            if plan:
                st.markdown("<div style='margin-top:1rem;'>", unsafe_allow_html=True)
                for task_item in plan:
                    status_task = task_item.get("status", "pending")
                    icon = {"done": "✓", "in_progress": "◉", "failed": "✗", "escalated": "⚠", "pending": "○"}.get(status_task, "○")
                    color = {"done": "#3fb950", "in_progress": "#388bfd", "failed": "#f85149", "escalated": "#d29922", "pending": "#484f58"}.get(status_task, "#484f58")
                    specialist = task_item.get("specialist", "")
                    st.markdown(f"""
                    <div style="display:flex;align-items:flex-start;gap:0.75rem;padding:0.75rem 1rem;background:#161b22;border:1px solid #21262d;border-radius:8px;margin-bottom:0.5rem;">
                        <span style="color:{color};font-size:1rem;margin-top:1px;font-weight:700;">{icon}</span>
                        <div style="flex:1;">
                            <div style="font-size:0.75rem;color:{color};font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.2rem;">{AGENT_ICONS.get(specialist,'🤖')} {specialist}</div>
                            <div style="font-size:0.88rem;color:#c9d1d9;">{task_item.get('description','')}</div>
                        </div>
                        <span style="font-size:0.72rem;color:#484f58;white-space:nowrap;">{task_item.get('complexity','')}</span>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            # HITL warning
            if s.get("awaiting_human"):
                st.markdown("""
                <div style="background:#1c1510;border:1px solid #d2992266;border-left:4px solid #d29922;border-radius:8px;padding:1rem 1.2rem;margin:1rem 0;display:flex;align-items:center;gap:0.8rem;">
                    <span style="font-size:1.3rem;">⏸️</span>
                    <div>
                        <div style="font-weight:600;color:#d29922;margin-bottom:0.2rem;">Awaiting Human Approval</div>
                        <div style="font-size:0.85rem;color:#8b949e;">An escalation has been raised. Review it in the <b>HITL Queue</b> tab.</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Errors
            if s.get("errors"):
                with st.expander(f"⚠️ {len(s['errors'])} error(s)"):
                    for err in s["errors"]:
                        st.code(err, language="text")

            # Final output
            if s.get("final_output"):
                st.markdown("""
                <div style="display:flex;align-items:center;gap:0.6rem;margin:1.5rem 0 0.8rem;">
                    <span style="font-size:1rem;">✅</span>
                    <span style="font-size:1.05rem;font-weight:700;color:#e6edf3;">Final Output</span>
                    <span style="font-size:0.78rem;color:#3fb950;background:#1f4a2e;padding:0.2rem 0.6rem;border-radius:4px;">score: {:.2f}</span>
                </div>
                """.format(score), unsafe_allow_html=True)
                st.markdown(
                    f'<div class="card" style="color:#c9d1d9;line-height:1.7;">{s["final_output"]}</div>',
                    unsafe_allow_html=True,
                )


# ════════════════════════════════════════════════════════════════════════
# PAGE: TASK MONITOR
# ════════════════════════════════════════════════════════════════════════
elif page == "Task Monitor":
    st.markdown("""
    <div class="page-header">
        <h1>📋 Task Monitor</h1>
        <p>All tasks — live status, token costs, and results.</p>
    </div>
    """, unsafe_allow_html=True)

    tasks = _api("/tasks") or []

    if not tasks:
        st.markdown("""
        <div style="text-align:center;padding:4rem 2rem;color:#484f58;">
            <div style="font-size:3rem;margin-bottom:1rem;">📭</div>
            <div style="font-size:1.1rem;font-weight:600;color:#8b949e;">No tasks yet</div>
            <div style="font-size:0.9rem;margin-top:0.5rem;">Submit a task to get started.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Summary row
        done_count    = sum(1 for t in tasks if t.get("status") == "done")
        failed_count  = sum(1 for t in tasks if t.get("status") == "failed")
        escalated_count = sum(1 for t in tasks if t.get("status") == "escalated")

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(metric_card("Total Tasks", str(len(tasks))), unsafe_allow_html=True)
        c2.markdown(metric_card("Completed", str(done_count), "✓ done"), unsafe_allow_html=True)
        c3.markdown(metric_card("Escalated", str(escalated_count), "⚠ human review"), unsafe_allow_html=True)
        c4.markdown(metric_card("Failed", str(failed_count), "✗ errors"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        for t in reversed(tasks):
            tid = t.get("task_id", t.get("id", ""))
            status = t.get("status", "unknown")
            req_text = t.get("request", "")[:90]

            with st.expander(f"  {req_text}  —  {tid}"):
                full = _api(f"/tasks/{tid}")
                if full:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.markdown(metric_card("Status", status.upper()), unsafe_allow_html=True)
                    c2.markdown(metric_card("Score", f"{full.get('reviewer_score',0):.2f}"), unsafe_allow_html=True)
                    c3.markdown(metric_card("Tokens", f"{full.get('total_tokens',0):,}"), unsafe_allow_html=True)
                    c4.markdown(metric_card("Tool Calls", str(full.get("total_tool_calls", 0))), unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)

                    plan = full.get("plan", [])
                    if plan:
                        st.markdown(pipeline_html(plan), unsafe_allow_html=True)

                    if full.get("final_output"):
                        st.markdown("**Output:**")
                        st.markdown(full["final_output"])


# ════════════════════════════════════════════════════════════════════════
# PAGE: HITL QUEUE
# ════════════════════════════════════════════════════════════════════════
elif page == "HITL Queue":
    st.markdown("""
    <div class="page-header">
        <h1>🔔 Human-in-the-Loop Queue</h1>
        <p>Review agent escalations. Approve to continue execution, reject to halt.</p>
    </div>
    """, unsafe_allow_html=True)

    pending_data = _api("/hitl/queue") or {}
    pending = pending_data.get("items", [])

    if not pending:
        st.markdown("""
        <div style="text-align:center;padding:3rem 2rem;">
            <div style="font-size:2.5rem;margin-bottom:0.8rem;">✅</div>
            <div style="font-size:1.05rem;font-weight:600;color:#3fb950;">Queue is clear</div>
            <div style="font-size:0.88rem;color:#484f58;margin-top:0.4rem;">No pending escalations.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background:#1c1510;border:1px solid #d2992244;border-radius:8px;padding:0.75rem 1.1rem;margin-bottom:1.2rem;display:flex;align-items:center;gap:0.7rem;">
            <span style="font-size:1.1rem;">⚠️</span>
            <span style="color:#d29922;font-weight:600;">{len(pending)} item{'s' if len(pending)!=1 else ''} awaiting review</span>
            <span style="color:#484f58;font-size:0.85rem;margin-left:0.3rem;">— execution is paused until resolved</span>
        </div>
        """, unsafe_allow_html=True)

        for item in pending:
            esc = item.get("escalation", {}) if "escalation" in item else item
            trigger = esc.get("trigger", "unknown").replace("_", " ").title()
            level   = esc.get("level", "approve_action")
            context = esc.get("context", {})
            task_id = item.get("task_id", "")
            task_req = item.get("task_request", "")[:160]
            item_id = item.get("id", "")

            level_colors = {
                "notify": "#388bfd", "approve_action": "#d29922",
                "approve_plan": "#f85149", "take_over": "#bc8cff",
            }
            lc = level_colors.get(level, "#8b949e")

            st.markdown(f"""
            <div class="hitl-card">
                <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.8rem;">
                    <span style="font-size:1.2rem;">🔔</span>
                    <div>
                        <div class="hitl-title">{trigger}</div>
                        <div class="hitl-meta">
                            Task <code style="background:#21262d;padding:0.1rem 0.4rem;border-radius:4px;font-size:0.78rem;">{task_id}</code>
                            &nbsp;·&nbsp;
                            <span style="color:{lc};font-weight:600;font-size:0.8rem;text-transform:uppercase;letter-spacing:0.04em;">{level}</span>
                        </div>
                    </div>
                </div>
                <div style="font-size:0.88rem;color:#8b949e;margin-bottom:0.8rem;padding:0.6rem 0.8rem;background:#0d1117;border-radius:6px;border-left:3px solid #30363d;">
                    {task_req}
                </div>
            </div>
            """, unsafe_allow_html=True)

            col_ctx, col_chat = st.columns([1, 1])
            with col_ctx:
                with st.expander("📋 Full Context"):
                    st.json(context)

            # ── Chat panel (clarification before approving) ─────── #
            with col_chat:
                st.markdown("**💬 Clarification Chat**", unsafe_allow_html=False)
                messages = (_api(f"/hitl/chat/{item_id}") or {}).get("messages", [])
                chat_container = st.container()
                with chat_container:
                    if not messages:
                        st.caption("No messages yet — ask the agent a question before deciding.")
                    for m in messages:
                        role_label = "🧑 You" if m["role"] == "human" else "🤖 Agent"
                        role_color = "#388bfd" if m["role"] == "human" else "#3fb950"
                        st.markdown(
                            f'<div style="margin-bottom:0.5rem;padding:0.5rem 0.75rem;background:#0d1117;'
                            f'border-left:3px solid {role_color};border-radius:0 6px 6px 0;font-size:0.85rem;">'
                            f'<span style="color:{role_color};font-weight:600;font-size:0.75rem;">{role_label}</span><br>'
                            f'{m["message"]}</div>',
                            unsafe_allow_html=True,
                        )
                chat_input = st.text_input("Ask a clarifying question:", key=f"chat_input_{item_id}",
                                           placeholder="e.g. What data sources did you use?")
                if st.button("Send", key=f"chat_send_{item_id}", use_container_width=True):
                    if chat_input.strip():
                        _api(f"/hitl/chat/{item_id}", method="POST",
                             json={"role": "human", "message": chat_input.strip()})
                        st.rerun()

            resp_key = f"resp_{item_id}"
            mod_key  = f"mod_{item_id}"
            response = st.text_area("Guidance / response for agent:", key=resp_key,
                                     placeholder="Optional — tell the agent what to do next...")
            modified = st.text_area("Override output (optional):", key=mod_key,
                                     placeholder="Paste a corrected output here to override the agent's result...")

            col_a, col_b, _ = st.columns([1, 1, 2])
            if col_a.button("✅ Approve", key=f"approve_{item_id}", type="primary", use_container_width=True):
                _api("/hitl/resolve", method="POST", json={
                    "item_id": item_id, "approved": True,
                    "response": response, "modified_output": modified,
                })
                st.rerun()
            if col_b.button("❌ Reject", key=f"reject_{item_id}", use_container_width=True):
                _api("/hitl/resolve", method="POST", json={
                    "item_id": item_id, "approved": False, "response": response,
                })
                st.rerun()

            st.markdown("<hr>", unsafe_allow_html=True)

    # Resolved history
    st.markdown("### Resolved History")
    resolved_data = _api("/hitl/resolved") or {}
    resolved = resolved_data.get("items", [])
    if not resolved:
        st.markdown('<div style="color:#484f58;font-size:0.9rem;">No resolved items yet.</div>', unsafe_allow_html=True)
    else:
        for item in resolved[:8]:
            is_approved = item.get("status") == "approved"
            esc = item.get("escalation", item)
            trigger = esc.get("trigger","unknown").replace("_"," ").title() if isinstance(esc, dict) else str(esc)
            icon = "✅" if is_approved else "❌"
            color = "#3fb950" if is_approved else "#f85149"
            ts = item.get("resolved_at") or item.get("created_at","")
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:0.7rem;padding:0.55rem 0.8rem;background:#161b22;border:1px solid #21262d;border-radius:7px;margin-bottom:0.4rem;font-size:0.85rem;">
                <span>{icon}</span>
                <code style="color:#8b949e;font-size:0.78rem;">{item.get('task_id','')}</code>
                <span style="color:#c9d1d9;">{trigger}</span>
                <span style="color:#484f58;margin-left:auto;font-size:0.78rem;">{str(ts)[:16]}</span>
            </div>
            """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE: TRACE EXPLORER
# ════════════════════════════════════════════════════════════════════════
elif page == "Trace Explorer":
    st.markdown("""
    <div class="page-header">
        <h1>🔭 Trace Explorer</h1>
        <p>Full decision log — every agent action, tool call, and routing decision.</p>
    </div>
    """, unsafe_allow_html=True)

    tasks = _api("/tasks") or []
    if not tasks:
        st.info("No tasks yet.")
    else:
        task_options = {
            f"{t.get('task_id',t.get('id',''))} — {t.get('request','')[:55]}": t.get('task_id', t.get('id',''))
            for t in reversed(tasks)
        }
        selected_label = st.selectbox("Select task", list(task_options.keys()),
                                       label_visibility="collapsed")
        selected_id = task_options[selected_label]

        full  = _api(f"/tasks/{selected_id}") or {}
        trace = (_api(f"/tasks/{selected_id}/trace") or {}).get("trace", [])

        if full:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.markdown(metric_card("Status",     full.get("status","—").upper()), unsafe_allow_html=True)
            c2.markdown(metric_card("Tokens",     f"{full.get('total_tokens',0):,}"), unsafe_allow_html=True)
            c3.markdown(metric_card("Tool Calls", str(full.get("total_tool_calls",0))), unsafe_allow_html=True)
            c4.markdown(metric_card("Score",      f"{full.get('reviewer_score',0):.2f}"), unsafe_allow_html=True)
            c5.markdown(metric_card("Cost",       f"${full.get('cost_usd',0):.4f}"), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

        # ── Replay / Step-through ─────────────────────────────────── #
        checkpoints_data = _api(f"/tasks/{selected_id}/checkpoints") or {}
        checkpoints = checkpoints_data.get("checkpoints", [])
        if checkpoints:
            st.markdown("#### 🎬 Step-Through Replay")
            step = st.slider(
                "Execution step",
                min_value=0,
                max_value=len(checkpoints) - 1,
                value=0,
                format="Step %d",
                key=f"replay_slider_{selected_id}",
            )
            cp = checkpoints[step]
            step_agent_color = {
                "supervisor": "#388bfd", "research": "#3fb950", "analysis": "#d29922",
                "writing": "#bc8cff", "code": "#f78166", "reviewer": "#79c0ff", "system": "#484f58",
            }.get(cp.get("agent", ""), "#8b949e")
            st.markdown(f"""
            <div class="card" style="border-left:3px solid {step_agent_color};">
                <div style="font-size:0.78rem;color:{step_agent_color};font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem;">
                    Step {step} · {cp.get('agent','').title()}
                </div>
                <div style="font-size:1rem;font-weight:600;color:#e6edf3;margin-bottom:0.6rem;">{cp.get('label','')}</div>
                <div style="font-size:0.82rem;color:#8b949e;">{json.dumps(cp.get('detail',{}), indent=2)[:300]}</div>
            </div>
            """, unsafe_allow_html=True)
            if cp.get("snapshot"):
                with st.expander("📸 State snapshot at this step"):
                    st.json(cp["snapshot"])

            # Replay button
            st.markdown("<br>", unsafe_allow_html=True)
            col_rp1, col_rp2 = st.columns([2, 1])
            with col_rp1:
                modified_req = st.text_input(
                    "Replay with modified request (optional):",
                    value="",
                    key=f"replay_req_{selected_id}",
                    placeholder="Leave blank to replay with original request",
                )
            with col_rp2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("▶ Replay Task", key=f"do_replay_{selected_id}", use_container_width=True):
                    result = _api(f"/tasks/{selected_id}/replay", method="POST",
                                  json={"modified_request": modified_req})
                    if result:
                        st.success(f"New task started: `{result.get('replay_task_id')}` — check Task Monitor")
                    else:
                        st.error("Replay failed — is the API running?")

            st.markdown("---", unsafe_allow_html=True)

        # Timeline
        if not trace:
            st.markdown('<div style="color:#484f58;text-align:center;padding:2rem;">No trace events yet.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f"**{len(trace)} events** recorded", unsafe_allow_html=True)
            st.markdown('<div class="timeline">', unsafe_allow_html=True)

            for event in trace:
                agent  = event.get("agent", "system")
                action = event.get("action", "")
                detail = event.get("detail")
                ts_raw = event.get("ts", 0)
                ts_str = time.strftime("%H:%M:%S", time.localtime(ts_raw))
                color_cls = AGENT_COLORS.get(agent, "c-system")
                icon = AGENT_ICONS.get(agent, "⚙️")

                # Build detail preview
                detail_str = ""
                if detail:
                    if isinstance(detail, dict):
                        detail_str = " · ".join(f"{k}: <b>{v}</b>" for k, v in list(detail.items())[:3])
                    else:
                        detail_str = str(detail)[:120]

                st.markdown(f"""
                <div class="timeline-event">
                    <div class="timeline-dot {color_cls}" style="color:inherit;"></div>
                    <div class="timeline-content">
                        <div class="timeline-header">
                            <span class="timeline-agent {color_cls}">{icon} {agent}</span>
                            <span class="timeline-time">{ts_str}</span>
                        </div>
                        <div class="timeline-action">{action.replace("_"," ")}</div>
                        {f'<div style="font-size:0.78rem;color:#484f58;margin-top:0.35rem;">{detail_str}</div>' if detail_str else ''}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if detail and isinstance(detail, dict) and len(detail) > 3:
                    with st.expander("Full detail"):
                        st.json(detail)

            st.markdown('</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE: MEMORY & TOOLS
# ════════════════════════════════════════════════════════════════════════
elif page == "Memory & Tools":
    st.markdown("""
    <div class="page-header">
        <h1>🧠 Memory & Tools</h1>
        <p>What the system remembers and how its tools are performing.</p>
    </div>
    """, unsafe_allow_html=True)

    stats = _api("/memory/stats") or {}
    logs  = (_api("/tools/logs") or {}).get("logs", [])

    # Memory stats
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### Long-Term Memory")
        mem_count = stats.get("long_term_memories", 0)
        st.markdown(f"""
        <div class="card card-purple" style="display:flex;align-items:center;gap:1.2rem;">
            <div style="font-size:2.5rem;">🧠</div>
            <div>
                <div style="font-size:2rem;font-weight:700;color:#bc8cff;font-family:'JetBrains Mono',monospace;">{mem_count}</div>
                <div style="font-size:0.85rem;color:#8b949e;">stored memories in ChromaDB</div>
                <div style="font-size:0.78rem;color:#484f58;margin-top:0.3rem;">{"Supabase ✓" if stats.get("supabase_enabled") else "Supabase not connected"}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="margin-top:1rem;font-size:0.82rem;color:#484f58;line-height:1.6;">
            <b style="color:#8b949e;">How it works:</b><br>
            After each task completes, the supervisor embeds a summary — what was asked,
            what approach worked, what tools were used. Future tasks query this store
            before planning so the system improves over time. Memories are scored by
            importance (reviewer score × complexity) and decay over 30 days.
        </div>
        """, unsafe_allow_html=True)

        # Memory management actions
        st.markdown("<br>", unsafe_allow_html=True)
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            if st.button("🔄 Consolidate Dupes", use_container_width=True):
                r = _api("/memory/consolidate", method="POST")
                if r:
                    st.success(f"Merged {r.get('merged_removed',0)} duplicates. {r.get('remaining',0)} remain.")
        with col_m2:
            if st.button("🗑️ Prune Old (90d)", use_container_width=True):
                r = _api("/memory/prune", method="POST")
                if r:
                    st.success(f"Pruned {r.get('pruned',0)} stale memories.")

        # Browse memories
        st.markdown("<br>**Recent Memories**", unsafe_allow_html=True)
        mem_list = (_api("/memory/list?limit=8") or {}).get("memories", [])
        if not mem_list:
            st.markdown('<div style="color:#484f58;font-size:0.85rem;">No memories yet. Run a task to populate.</div>', unsafe_allow_html=True)
        for m in mem_list:
            meta = m.get("metadata", {})
            imp  = float(meta.get("importance", 0.5))
            imp_color = "#3fb950" if imp >= 0.7 else "#d29922" if imp >= 0.4 else "#484f58"
            with st.expander(f"📌 {m['content'][:80]}…", expanded=False):
                st.markdown(f"**Importance:** <span style='color:{imp_color}'>{imp:.2f}</span> &nbsp;|&nbsp; **Task:** `{meta.get('task_id','—')}` &nbsp;|&nbsp; **User:** `{meta.get('user_id','—')}`", unsafe_allow_html=True)
                st.caption(m["content"])
                if st.button(f"Delete {m['id'][:8]}", key=f"del_{m['id']}"):
                    _api(f"/memory/{m['id']}", method="DELETE")
                    st.rerun()

    with col_r:
        st.markdown("#### Tool Performance")
        if not logs:
            st.markdown('<div style="color:#484f58;padding:2rem;text-align:center;">No tool calls yet.</div>', unsafe_allow_html=True)
        else:
            # Summary metrics
            total_calls = len(logs)
            success_count = sum(1 for l in logs if l.get("success"))
            avg_latency = sum(l.get("latency_s", 0) for l in logs) / max(total_calls, 1)

            mc1, mc2, mc3 = st.columns(3)
            mc1.markdown(metric_card("Total Calls", str(total_calls)), unsafe_allow_html=True)
            mc2.markdown(metric_card("Success Rate", f"{100*success_count//max(total_calls,1)}%"), unsafe_allow_html=True)
            mc3.markdown(metric_card("Avg Latency", f"{avg_latency:.2f}s"), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Tool call log table
            for log_entry in reversed(logs[-12:]):
                success = log_entry.get("success", False)
                icon    = "✓" if success else "✗"
                color   = "#3fb950" if success else "#f85149"
                tool    = log_entry.get("tool_name", log_entry.get("tool",""))
                agent   = log_entry.get("agent","")
                latency = log_entry.get("latency_s", 0)
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:0.7rem;padding:0.5rem 0.8rem;background:#161b22;border:1px solid #21262d;border-radius:6px;margin-bottom:0.35rem;font-size:0.82rem;">
                    <span style="color:{color};font-weight:700;width:14px;">{icon}</span>
                    <span style="color:#e6edf3;font-weight:600;min-width:120px;">{tool}</span>
                    <span style="color:#484f58;">→</span>
                    <span style="color:#8b949e;">{agent}</span>
                    <span style="color:#484f58;margin-left:auto;font-family:'JetBrains Mono',monospace;">{latency:.3f}s</span>
                </div>
                """, unsafe_allow_html=True)

    # Tool usage chart
    if logs:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Usage by Tool")
        try:
            import pandas as pd
            import plotly.express as px

            tool_counts: dict = {}
            for l in logs:
                t = l.get("tool_name", l.get("tool","unknown"))
                tool_counts[t] = tool_counts.get(t, 0) + 1

            df = pd.DataFrame(list(tool_counts.items()), columns=["Tool", "Calls"])
            fig = px.bar(
                df.sort_values("Calls", ascending=True),
                x="Calls", y="Tool", orientation="h",
                color="Calls",
                color_continuous_scale=["#1a2d4a", "#388bfd"],
            )
            fig.update_layout(
                plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                font_color="#8b949e", showlegend=False,
                coloraxis_showscale=False,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(gridcolor="#21262d", zeroline=False),
                yaxis=dict(gridcolor="rgba(0,0,0,0)"),
                height=220,
            )
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            pass


# ════════════════════════════════════════════════════════════════════════
# PAGE: ANALYTICS
# ════════════════════════════════════════════════════════════════════════
elif page == "Analytics":
    st.markdown("""
    <div class="page-header">
        <h1>📈 Analytics</h1>
        <p>Aggregate cost, model usage, escalation rates, and tool patterns across all tasks.</p>
    </div>
    """, unsafe_allow_html=True)

    agg = _api("/stats/aggregate") or {}

    if agg.get("total_tasks", 0) == 0:
        st.info("No tasks completed yet. Run some tasks to see analytics.")
    else:
        # ── Top-line KPIs ──────────────────────────────────────────── #
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.markdown(metric_card("Total Tasks",    str(agg["total_tasks"])), unsafe_allow_html=True)
        k2.markdown(metric_card("Completed",      str(agg["completed_tasks"])), unsafe_allow_html=True)
        k3.markdown(metric_card("Total Cost",     f"${agg['total_cost_usd']:.4f}"), unsafe_allow_html=True)
        k4.markdown(metric_card("Avg Cost/Task",  f"${agg['avg_cost_usd']:.4f}"), unsafe_allow_html=True)
        k5.markdown(metric_card("Escalation Rate", f"{agg['escalation_rate']*100:.1f}%"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        col_a, col_b = st.columns(2)

        # ── Model usage breakdown ──────────────────────────────────── #
        with col_a:
            st.markdown("#### Model Usage (tokens)")
            model_usage = agg.get("model_usage", {})
            if model_usage:
                try:
                    import pandas as pd
                    import plotly.express as px

                    df_m = pd.DataFrame([
                        {"Model": m, "Tokens": t}
                        for m, t in model_usage.items()
                    ])
                    fig_m = px.pie(
                        df_m, names="Model", values="Tokens",
                        color_discrete_sequence=["#388bfd", "#3fb950", "#bc8cff", "#d29922"],
                    )
                    fig_m.update_layout(
                        plot_bgcolor="#0d1117", paper_bgcolor="#161b22",
                        font_color="#8b949e", showlegend=True,
                        legend=dict(font=dict(color="#8b949e")),
                        margin=dict(l=0, r=0, t=20, b=0),
                        height=260,
                    )
                    fig_m.update_traces(textfont_color="#e6edf3")
                    st.plotly_chart(fig_m, use_container_width=True)

                    # Cost per model
                    from agents.base import MODEL_COST_PER_1K
                    for model, tokens in model_usage.items():
                        rate = MODEL_COST_PER_1K.get(model, 0.010)
                        cost = tokens * rate / 1000
                        st.markdown(
                            f'<div style="display:flex;justify-content:space-between;font-size:0.82rem;padding:0.3rem 0.5rem;border-bottom:1px solid #21262d;">'
                            f'<span style="color:#8b949e;">{model}</span>'
                            f'<span style="color:#e6edf3;font-family:monospace;">{tokens:,} tok &nbsp;≈&nbsp; ${cost:.4f}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                except ImportError:
                    for m, t in model_usage.items():
                        st.write(f"{m}: {t:,} tokens")
            else:
                st.caption("No model usage data yet.")

        # ── Tool usage patterns ────────────────────────────────────── #
        with col_b:
            st.markdown("#### Tool Usage Patterns")
            tool_usage = agg.get("tool_usage", {})
            if tool_usage:
                try:
                    import pandas as pd
                    import plotly.express as px

                    df_t = pd.DataFrame([
                        {"Tool": t, "Calls": c}
                        for t, c in tool_usage.items()
                    ]).sort_values("Calls", ascending=True)
                    fig_t = px.bar(
                        df_t, x="Calls", y="Tool", orientation="h",
                        color="Calls",
                        color_continuous_scale=["#1f3a2e", "#3fb950"],
                    )
                    fig_t.update_layout(
                        plot_bgcolor="#0d1117", paper_bgcolor="#161b22",
                        font_color="#8b949e", showlegend=False,
                        coloraxis_showscale=False,
                        margin=dict(l=0, r=0, t=10, b=0),
                        xaxis=dict(gridcolor="#21262d", zeroline=False),
                        yaxis=dict(gridcolor="rgba(0,0,0,0)"),
                        height=260,
                    )
                    fig_t.update_traces(marker_line_width=0)
                    st.plotly_chart(fig_t, use_container_width=True)
                except ImportError:
                    for t, c in tool_usage.items():
                        st.write(f"{t}: {c} calls")
            else:
                st.caption("No tool usage data yet.")

        # ── Performance summary ────────────────────────────────────── #
        st.markdown("<br>#### Performance Summary", unsafe_allow_html=True)
        p1, p2, p3, p4 = st.columns(4)
        p1.markdown(metric_card("Avg Tokens/Task",   f"{agg['avg_tokens']:,}"), unsafe_allow_html=True)
        p2.markdown(metric_card("Avg Review Score",  f"{agg['avg_reviewer_score']:.2f}"), unsafe_allow_html=True)
        p3.markdown(metric_card("Avg Wall Time",     f"{agg['avg_wall_time_s']:.1f}s"), unsafe_allow_html=True)
        p4.markdown(metric_card("Failed Tasks",      str(agg["failed_tasks"])), unsafe_allow_html=True)

        # ── Escalation breakdown ───────────────────────────────────── #
        if agg["escalated_tasks"] > 0:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class="card card-warning">
                <b style="color:#d29922;">⚠ Escalations</b>&nbsp;
                <span style="color:#8b949e;">{agg['escalated_tasks']} task(s) required human review
                ({agg['escalation_rate']*100:.1f}% rate)</span>
            </div>
            """, unsafe_allow_html=True)
