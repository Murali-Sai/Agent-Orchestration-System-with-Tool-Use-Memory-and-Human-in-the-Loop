"""Agent Orchestration System — UI"""
from __future__ import annotations
import os, time, json
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

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

if st.session_state.get("active_task"):
    st_autorefresh(interval=3000, key="poll")

# ════════════════════════════════════════════════════════════════════════
# GLOBAL CSS
# ════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Reset & base ── */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.main .block-container { padding: 2rem 2.5rem 4rem; max-width: 1400px; }
h1,h2,h3,h4,h5,h6 { font-family: 'Inter', sans-serif !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #080c14; }
::-webkit-scrollbar-thumb { background: #1e2b3c; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #2d3f58; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #080c14 !important;
    border-right: 1px solid #1e2b3c !important;
}
[data-testid="stSidebar"] > div { padding-top: 0 !important; }

/* Hide radio dots */
[data-testid="stSidebar"] .stRadio > label { display: none !important; }
[data-testid="stSidebar"] .stRadio > div { display: flex; flex-direction: column; gap: 2px; }
[data-testid="stSidebar"] .stRadio label { margin: 0 !important; padding: 0 !important; }
[data-testid="stSidebar"] .stRadio label > div:first-child { display: none !important; }
[data-testid="stSidebar"] .stRadio label > div:last-child {
    padding: 0.6rem 1rem !important;
    border-radius: 8px !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: #64748b !important;
    cursor: pointer !important;
    transition: all 0.15s ease !important;
    width: 100% !important;
}
[data-testid="stSidebar"] .stRadio label > div:last-child:hover {
    color: #e2e8f0 !important;
    background: #0f1623 !important;
}
[data-testid="stSidebar"] .stRadio [aria-checked="true"] > div:last-child {
    color: #60a5fa !important;
    background: #0f1f3d !important;
    font-weight: 600 !important;
}

/* ── Inputs ── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background: #0a0f1a !important;
    border: 1px solid #1e2b3c !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9rem !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,0.15) !important;
    outline: none !important;
}
[data-testid="stTextInput"] label,
[data-testid="stTextArea"] label { color: #94a3b8 !important; font-size: 0.82rem !important; font-weight: 500 !important; }

/* ── Buttons ── */
[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    letter-spacing: 0.02em !important;
    box-shadow: 0 4px 15px rgba(59,130,246,0.3) !important;
    transition: all 0.2s !important;
}
[data-testid="baseButton-primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(59,130,246,0.4) !important;
}
[data-testid="baseButton-secondary"] {
    background: #0f1623 !important;
    border: 1px solid #1e2b3c !important;
    color: #94a3b8 !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    transition: all 0.2s !important;
}
[data-testid="baseButton-secondary"]:hover {
    border-color: #3b82f6 !important;
    color: #e2e8f0 !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #0f1623 !important;
    border: 1px solid #1e2b3c !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary { color: #94a3b8 !important; font-size: 0.875rem !important; }

/* ── Select box ── */
[data-testid="stSelectbox"] > div > div {
    background: #0a0f1a !important;
    border: 1px solid #1e2b3c !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
}

/* ── Slider ── */
[data-testid="stSlider"] > div > div > div > div { background: #3b82f6 !important; }

/* ── Divider ── */
hr { border-color: #1e2b3c !important; margin: 1.2rem 0 !important; }

/* ── Alerts ── */
[data-testid="stAlert"] { border-radius: 10px !important; }

/* ── Card components ── */
.card {
    background: #0f1623;
    border: 1px solid #1e2b3c;
    border-radius: 14px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 0.9rem;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.card:hover { border-color: rgba(59,130,246,0.3); }
.card-blue   { border-left: 3px solid #3b82f6; }
.card-green  { border-left: 3px solid #10b981; }
.card-yellow { border-left: 3px solid #f59e0b; }
.card-red    { border-left: 3px solid #ef4444; }
.card-purple { border-left: 3px solid #8b5cf6; }

/* ── Hero header ── */
.page-hero {
    background: linear-gradient(135deg, #0f1623 0%, #0a1628 50%, #080c14 100%);
    border: 1px solid #1e2b3c;
    border-radius: 16px;
    padding: 2rem 2.2rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}
.page-hero::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, #3b82f6, #8b5cf6, transparent);
}
.page-hero h1 { font-size: 1.6rem; font-weight: 800; color: #f0f6ff; margin: 0 0 0.4rem; letter-spacing: -0.02em; }
.page-hero p  { color: #64748b; margin: 0; font-size: 0.9rem; line-height: 1.5; }

/* ── Status badges ── */
.badge {
    display: inline-flex; align-items: center; gap: 0.3rem;
    padding: 0.18rem 0.7rem;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.badge-done     { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.25); }
.badge-running  { background: rgba(59,130,246,0.12);  color: #60a5fa; border: 1px solid rgba(59,130,246,0.25); }
.badge-planning { background: rgba(139,92,246,0.12); color: #a78bfa; border: 1px solid rgba(139,92,246,0.25); }
.badge-failed   { background: rgba(239,68,68,0.12);  color: #f87171; border: 1px solid rgba(239,68,68,0.25); }
.badge-escalated{ background: rgba(245,158,11,0.12); color: #fbbf24; border: 1px solid rgba(245,158,11,0.25); }
.badge-pending  { background: rgba(100,116,139,0.1); color: #64748b; border: 1px solid rgba(100,116,139,0.2); }

/* ── Metric cards ── */
.metric-card {
    background: #0f1623;
    border: 1px solid #1e2b3c;
    border-radius: 12px;
    padding: 1.1rem 1.2rem;
    text-align: center;
    transition: border-color 0.2s;
}
.metric-card:hover { border-color: rgba(59,130,246,0.25); }
.metric-card .m-label { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.5rem; font-weight: 600; }
.metric-card .m-value { font-size: 1.75rem; font-weight: 800; color: #f0f6ff; font-family: 'JetBrains Mono', monospace; letter-spacing: -0.02em; }
.metric-card .m-sub   { font-size: 0.72rem; color: #334155; margin-top: 0.25rem; }

/* ── Agent pipeline ── */
.pipeline { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.8rem 0; align-items: center; }
.agent-chip {
    display: flex; align-items: center; gap: 0.45rem;
    padding: 0.4rem 0.9rem;
    border-radius: 8px;
    font-size: 0.78rem;
    font-weight: 600;
    border: 1px solid;
    transition: all 0.2s;
}
.agent-chip.done        { background: rgba(16,185,129,0.1);  color: #10b981; border-color: rgba(16,185,129,0.2); }
.agent-chip.in_progress { background: rgba(59,130,246,0.15); color: #60a5fa; border-color: #3b82f6; animation: glow-pulse 2s infinite; }
.agent-chip.pending     { background: rgba(30,43,60,0.5);    color: #334155; border-color: #1e2b3c; }
.agent-chip.failed      { background: rgba(239,68,68,0.1);   color: #f87171; border-color: rgba(239,68,68,0.2); }
.chip-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.pipe-arrow { color: #1e2b3c; font-size: 1rem; }

@keyframes glow-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(59,130,246,0.4); }
    50%       { box-shadow: 0 0 0 6px rgba(59,130,246,0.05); }
}

/* ── Timeline trace ── */
.timeline { position: relative; padding-left: 1.6rem; }
.timeline::before {
    content: '';
    position: absolute; left: 0.45rem; top: 0.5rem; bottom: 0;
    width: 1px; background: linear-gradient(to bottom, #1e2b3c, transparent);
}
.timeline-event { position: relative; margin-bottom: 1rem; }
.timeline-dot {
    position: absolute; left: -1.25rem; top: 0.4rem;
    width: 9px; height: 9px; border-radius: 50%;
    border: 2px solid currentColor; background: #080c14;
}
.timeline-content {
    background: #0f1623; border: 1px solid #1e2b3c;
    border-radius: 10px; padding: 0.75rem 1rem;
    transition: border-color 0.2s;
}
.timeline-content:hover { border-color: #2d3f58; }
.timeline-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem; }
.timeline-agent { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
.timeline-time  { font-size: 0.7rem; color: #334155; font-family: 'JetBrains Mono', monospace; }
.timeline-action { font-size: 0.83rem; color: #64748b; }

/* Agent accent colours */
.ac-supervisor { color: #60a5fa; }
.ac-research   { color: #10b981; }
.ac-analysis   { color: #f59e0b; }
.ac-writing    { color: #a78bfa; }
.ac-code       { color: #fb923c; }
.ac-reviewer   { color: #38bdf8; }
.ac-system     { color: #334155; }

/* ── HITL card ── */
.hitl-card {
    background: #120f06;
    border: 1px solid rgba(245,158,11,0.2);
    border-left: 3px solid #f59e0b;
    border-radius: 14px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.2rem;
}

/* ── Capability chips ── */
.cap-chip {
    display: inline-flex; align-items: center; gap: 0.4rem;
    padding: 0.35rem 0.85rem;
    border-radius: 8px;
    font-size: 0.78rem; font-weight: 600;
    transition: all 0.2s; cursor: default;
}
.cap-chip:hover { transform: translateY(-1px); }

/* ── Progress bar ── */
.progress-wrap { margin-bottom: 1rem; }
.progress-label { display: flex; justify-content: space-between; font-size: 0.75rem; color: #64748b; margin-bottom: 0.4rem; }
.progress-track { background: #1e2b3c; border-radius: 10px; height: 6px; overflow: hidden; }
.progress-fill  { background: linear-gradient(90deg, #3b82f6, #8b5cf6); height: 100%; border-radius: 10px; transition: width 0.6s ease; }

/* ── Section heading ── */
.section-heading {
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: #334155; margin: 1.5rem 0 0.8rem;
}
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
    dot = {"done": "●", "running": "●", "executing": "●", "reviewing": "●"}.get(status, "")
    return f'<span class="badge {cls}">{dot} {status}</span>' if dot else f'<span class="badge {cls}">{status}</span>'


def metric_card(label: str, value: str, sub: str = "", accent: str = "") -> str:
    border = f"border-top: 2px solid {accent};" if accent else ""
    return f"""
    <div class="metric-card" style="{border}">
        <div class="m-label">{label}</div>
        <div class="m-value">{value}</div>
        {f'<div class="m-sub">{sub}</div>' if sub else ''}
    </div>"""


AGENT_ICONS = {
    "supervisor": "🧠", "research": "🔍", "analysis": "📊",
    "writing": "✍️", "code": "💻", "reviewer": "🔎", "system": "⚙️",
}
AGENT_COLORS = {
    "supervisor": "ac-supervisor", "research": "ac-research", "analysis": "ac-analysis",
    "writing": "ac-writing", "code": "ac-code", "reviewer": "ac-reviewer", "system": "ac-system",
}
AGENT_HEX = {
    "supervisor": "#60a5fa", "research": "#10b981", "analysis": "#f59e0b",
    "writing": "#a78bfa", "code": "#fb923c", "reviewer": "#38bdf8", "system": "#334155",
}


def pipeline_html(plan: list) -> str:
    if not plan:
        return ""
    chips = []
    for i, st_task in enumerate(plan):
        status = st_task.get("status", "pending")
        specialist = st_task.get("specialist", "agent")
        chips.append(
            f'<div class="agent-chip {status}">'
            f'<span class="chip-dot"></span>'
            f'{AGENT_ICONS.get(specialist, "🤖")} {specialist.title()}'
            f'</div>'
        )
        if i < len(plan) - 1:
            chips.append('<span class="pipe-arrow">›</span>')
    return f'<div class="pipeline">{"".join(chips)}</div>'


def _api(path: str, method="GET", timeout=10, **kwargs):
    try:
        fn = getattr(requests, method.lower())
        return fn(f"{API}{path}", timeout=timeout, **kwargs).json()
    except Exception:
        return None


def _api_health():
    for t in (8, 30):
        h = _api("/health", timeout=t)
        if h:
            return h
    return None


# ════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # Logo / brand
    st.markdown("""
    <div style="padding: 1.8rem 1.2rem 1.2rem; border-bottom: 1px solid #1e2b3c;">
        <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem;">
            <div style="
                width:36px; height:36px; border-radius:10px;
                background: linear-gradient(135deg, #3b82f6, #8b5cf6);
                display:flex; align-items:center; justify-content:center;
                font-size:1.1rem; box-shadow: 0 4px 12px rgba(59,130,246,0.4);
                flex-shrink:0;
            ">⚡</div>
            <div>
                <div style="font-size:0.88rem; font-weight:700; color:#f0f6ff; line-height:1.2;">Agent OS</div>
                <div style="font-size:0.65rem; color:#334155; letter-spacing:0.04em;">ORCHESTRATION SYSTEM</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div style="padding: 0.8rem 0.6rem 0.4rem;"><div class="section-heading">Navigation</div></div>', unsafe_allow_html=True)

    page = st.radio(
        "nav",
        ["⚡  Submit Task", "📋  Task Monitor", "🔔  HITL Queue",
         "🔭  Trace Explorer", "🧠  Memory & Tools", "📈  Analytics"],
        label_visibility="collapsed",
    )
    page = page.split("  ", 1)[1]

    st.markdown('<div style="padding: 0.4rem 0.6rem 0;"><div class="section-heading">System Status</div></div>', unsafe_allow_html=True)

    health = _api_health()
    if health:
        active  = health.get("tasks_active", 0)
        sb_ok   = health.get("supabase", False)
        cel_ok  = health.get("celery", False)

        def _status_row(ok, label, sub=""):
            dot_color = "#10b981" if ok else "#334155"
            text_color = "#10b981" if ok else "#64748b"
            label_text = label + (" ✓" if ok else "")
            return f"""
            <div style="display:flex;align-items:center;gap:0.6rem;padding:0.45rem 0.6rem;border-radius:8px;background:{'rgba(16,185,129,0.06)' if ok else 'transparent'};">
                <span style="width:7px;height:7px;border-radius:50%;background:{dot_color};flex-shrink:0;{'box-shadow:0 0 6px #10b981;' if ok else ''}"></span>
                <span style="font-size:0.8rem;color:{text_color};font-weight:{'600' if ok else '400'};">{label_text}</span>
                {f'<span style="font-size:0.72rem;color:#334155;margin-left:auto;">{sub}</span>' if sub else ''}
            </div>"""

        st.markdown(f"""
        <div style="padding:0.2rem 0.4rem; display:flex; flex-direction:column; gap:2px;">
            {_status_row(True, "API Online", f"{active} active")}
            {_status_row(sb_ok, "Supabase")}
            {_status_row(cel_ok, "Celery")}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="padding:0.4rem 0.6rem;">
            <div style="display:flex;align-items:center;gap:0.6rem;padding:0.5rem 0.6rem;border-radius:8px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.15);">
                <span style="width:7px;height:7px;border-radius:50%;background:#f59e0b;animation:glow-pulse 2s infinite;flex-shrink:0;"></span>
                <span style="font-size:0.8rem;color:#f59e0b;font-weight:600;">Waking up…</span>
            </div>
            <div style="font-size:0.7rem;color:#334155;padding:0.4rem 0.6rem;line-height:1.5;">
                Free tier cold start — takes 30–60s on first visit.
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Footer
    st.markdown("""
    <div style="position:absolute;bottom:1.2rem;left:0;right:0;padding:0 1.2rem;border-top:1px solid #1e2b3c;padding-top:0.8rem;">
        <div style="font-size:0.65rem;color:#334155;line-height:1.6;">
            LangGraph · OpenAI GPT-4o<br>
            Redis · Supabase pgvector
        </div>
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE: SUBMIT TASK
# ════════════════════════════════════════════════════════════════════════
if page == "Submit Task":

    # Hero
    st.markdown("""
    <div class="page-hero">
        <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.5rem;">
            <span style="font-size:1.5rem;">⚡</span>
            <h1 style="margin:0;">Submit a Task</h1>
        </div>
        <p>Describe your goal in plain English. The Supervisor decomposes it, assigns specialists, and delivers a synthesized result.</p>
    </div>
    """, unsafe_allow_html=True)

    # Capability chips
    caps = [
        ("🔍", "Web Research",   "#10b981", "rgba(16,185,129,0.08)",  "rgba(16,185,129,0.2)"),
        ("📊", "Data Analysis",  "#f59e0b", "rgba(245,158,11,0.08)",  "rgba(245,158,11,0.2)"),
        ("✍️", "Writing",        "#a78bfa", "rgba(139,92,246,0.08)",  "rgba(139,92,246,0.2)"),
        ("💻", "Code Execution", "#fb923c", "rgba(251,146,60,0.08)",  "rgba(251,146,60,0.2)"),
        ("🔎", "Quality Review", "#38bdf8", "rgba(56,189,248,0.08)",  "rgba(56,189,248,0.2)"),
    ]
    chips_html = "".join(
        f'<span class="cap-chip" style="color:{c};background:{bg};border:1px solid {bd};">{icon} {name}</span>'
        for icon, name, c, bg, bd in caps
    )
    st.markdown(f'<div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1.5rem;">{chips_html}</div>',
                unsafe_allow_html=True)

    # Task form
    with st.form("task_form", clear_on_submit=False):
        request = st.text_area(
            "What do you want to accomplish?",
            height=120,
            placeholder="e.g. Research the top 5 AI startups of 2025, analyze their funding and tech stack, and write an investor brief.",
        )
        col_uid, col_btn = st.columns([3, 1])
        with col_uid:
            user_id = st.text_input("", value="demo_user", label_visibility="collapsed", placeholder="User ID")
        with col_btn:
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
            status      = s.get("status", "unknown")
            completed   = s.get("completed", 0)
            total       = s.get("total", 0)
            tokens      = s.get("total_tokens", 0)
            score       = s.get("reviewer_score", 0)
            tool_calls  = s.get("total_tool_calls", 0)
            confidence  = s.get("plan_confidence", 0)

            st.markdown("<hr>", unsafe_allow_html=True)

            # Task header
            h1, h2 = st.columns([6, 1])
            with h1:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:1.2rem;">'
                    f'<span style="font-size:0.82rem;color:#64748b;font-family:monospace;">TASK</span>'
                    f'<code style="background:#0f1623;border:1px solid #1e2b3c;padding:0.2rem 0.6rem;border-radius:6px;font-size:0.82rem;color:#94a3b8;">{task_id}</code>'
                    f'{badge(status)}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with h2:
                if st.button("Clear", use_container_width=True):
                    st.session_state.pop("active_task", None)
                    st.session_state.pop("active_request", None)
                    st.rerun()

            # Metrics
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.markdown(metric_card("Subtasks",    f"{completed}/{total}", accent="#3b82f6"), unsafe_allow_html=True)
            c2.markdown(metric_card("Tokens",      f"{tokens:,}",          accent="#8b5cf6"), unsafe_allow_html=True)
            c3.markdown(metric_card("Tool Calls",  str(tool_calls),        accent="#10b981"), unsafe_allow_html=True)
            c4.markdown(metric_card("Score",       f"{score:.2f}" if score else "—", accent="#f59e0b"), unsafe_allow_html=True)
            c5.markdown(metric_card("Confidence",  f"{confidence:.2f}",    accent="#38bdf8"), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Progress bar
            if total > 0:
                pct = int((completed / total) * 100)
                st.markdown(f"""
                <div class="progress-wrap">
                    <div class="progress-label">
                        <span>Execution Progress</span><span style="color:#3b82f6;font-weight:600;">{pct}%</span>
                    </div>
                    <div class="progress-track">
                        <div class="progress-fill" style="width:{pct}%;"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Pipeline
            plan = s.get("plan", [])
            if plan:
                st.markdown(pipeline_html(plan), unsafe_allow_html=True)

            # Subtask list
            if plan:
                st.markdown('<div class="section-heading" style="margin-top:1.2rem;">Subtasks</div>', unsafe_allow_html=True)
                for task_item in plan:
                    st_status = task_item.get("status", "pending")
                    specialist = task_item.get("specialist", "")
                    color = {
                        "done": "#10b981", "in_progress": "#60a5fa",
                        "failed": "#f87171", "escalated": "#fbbf24", "pending": "#334155"
                    }.get(st_status, "#334155")
                    icon = {"done": "✓", "in_progress": "◉", "failed": "✗", "escalated": "⚠", "pending": "○"}.get(st_status, "○")
                    bg = {
                        "done": "rgba(16,185,129,0.05)", "in_progress": "rgba(59,130,246,0.08)",
                        "failed": "rgba(239,68,68,0.05)"
                    }.get(st_status, "transparent")
                    st.markdown(f"""
                    <div style="display:flex;align-items:flex-start;gap:0.8rem;padding:0.8rem 1rem;background:{bg};border:1px solid #1e2b3c;border-left:2px solid {color};border-radius:10px;margin-bottom:0.4rem;transition:all 0.2s;">
                        <span style="color:{color};font-size:0.9rem;margin-top:1px;font-weight:700;min-width:14px;">{icon}</span>
                        <div style="flex:1;min-width:0;">
                            <div style="font-size:0.7rem;color:{color};font-weight:700;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">{AGENT_ICONS.get(specialist,'🤖')} {specialist}</div>
                            <div style="font-size:0.875rem;color:#94a3b8;line-height:1.4;">{task_item.get('description','')}</div>
                        </div>
                        <span style="font-size:0.68rem;color:#334155;white-space:nowrap;padding:0.2rem 0.5rem;background:#0a0f1a;border-radius:4px;">{task_item.get('complexity','')}</span>
                    </div>
                    """, unsafe_allow_html=True)

            # HITL warning
            if s.get("awaiting_human"):
                st.markdown("""
                <div style="background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.2);border-left:3px solid #f59e0b;border-radius:12px;padding:1rem 1.2rem;margin:1.2rem 0;display:flex;align-items:center;gap:1rem;">
                    <span style="font-size:1.4rem;">⏸️</span>
                    <div>
                        <div style="font-weight:700;color:#fbbf24;margin-bottom:0.2rem;font-size:0.9rem;">Awaiting Human Approval</div>
                        <div style="font-size:0.82rem;color:#64748b;">An escalation has been raised — review it in the <b style="color:#94a3b8;">HITL Queue</b>.</div>
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
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:0.8rem;margin:1.8rem 0 1rem;">
                    <div style="width:28px;height:28px;border-radius:8px;background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.3);display:flex;align-items:center;justify-content:center;font-size:0.85rem;">✅</div>
                    <span style="font-size:1rem;font-weight:700;color:#f0f6ff;">Final Output</span>
                    <span style="font-size:0.72rem;color:#10b981;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.2);padding:0.18rem 0.6rem;border-radius:6px;font-family:monospace;">score {score:.2f}</span>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(
                    f'<div class="card" style="color:#94a3b8;line-height:1.75;font-size:0.9rem;">{s["final_output"]}</div>',
                    unsafe_allow_html=True,
                )


# ════════════════════════════════════════════════════════════════════════
# PAGE: TASK MONITOR
# ════════════════════════════════════════════════════════════════════════
elif page == "Task Monitor":
    st.markdown("""
    <div class="page-hero">
        <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.5rem;">
            <span style="font-size:1.5rem;">📋</span>
            <h1 style="margin:0;">Task Monitor</h1>
        </div>
        <p>All tasks with live status, token costs, and full results.</p>
    </div>
    """, unsafe_allow_html=True)

    tasks = _api("/tasks") or []

    if not tasks:
        st.markdown("""
        <div style="text-align:center;padding:5rem 2rem;">
            <div style="font-size:3rem;margin-bottom:1rem;opacity:0.4;">📭</div>
            <div style="font-size:1rem;font-weight:600;color:#334155;">No tasks yet</div>
            <div style="font-size:0.85rem;color:#1e2b3c;margin-top:0.5rem;">Submit a task to get started.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        done_count      = sum(1 for t in tasks if t.get("status") == "done")
        failed_count    = sum(1 for t in tasks if t.get("status") == "failed")
        escalated_count = sum(1 for t in tasks if t.get("status") == "escalated")
        running_count   = sum(1 for t in tasks if t.get("status") not in ("done","failed","escalated"))

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(metric_card("Total Tasks", str(len(tasks)),          accent="#3b82f6"), unsafe_allow_html=True)
        c2.markdown(metric_card("Completed",   str(done_count),          accent="#10b981"), unsafe_allow_html=True)
        c3.markdown(metric_card("Escalated",   str(escalated_count),     accent="#f59e0b"), unsafe_allow_html=True)
        c4.markdown(metric_card("Failed",      str(failed_count),        accent="#ef4444"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        for t in reversed(tasks):
            tid      = t.get("task_id", t.get("id", ""))
            status   = t.get("status", "unknown")
            req_text = t.get("request", "")[:80]
            sc       = t.get("reviewer_score", 0)

            status_color = {
                "done": "#10b981", "failed": "#ef4444",
                "escalated": "#f59e0b"
            }.get(status, "#3b82f6")

            with st.expander(f"{req_text}  —  {tid}"):
                full = _api(f"/tasks/{tid}")
                if full:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.markdown(metric_card("Status",     status.upper(),                          accent=status_color), unsafe_allow_html=True)
                    c2.markdown(metric_card("Score",      f"{full.get('reviewer_score',0):.2f}",   accent="#f59e0b"),    unsafe_allow_html=True)
                    c3.markdown(metric_card("Tokens",     f"{full.get('total_tokens',0):,}",       accent="#8b5cf6"),    unsafe_allow_html=True)
                    c4.markdown(metric_card("Tool Calls", str(full.get("total_tool_calls", 0)),    accent="#10b981"),    unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)
                    plan = full.get("plan", [])
                    if plan:
                        st.markdown(pipeline_html(plan), unsafe_allow_html=True)
                    if full.get("final_output"):
                        st.markdown('<div class="section-heading">Output</div>', unsafe_allow_html=True)
                        st.markdown(full["final_output"])


# ════════════════════════════════════════════════════════════════════════
# PAGE: HITL QUEUE
# ════════════════════════════════════════════════════════════════════════
elif page == "HITL Queue":
    st.markdown("""
    <div class="page-hero">
        <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.5rem;">
            <span style="font-size:1.5rem;">🔔</span>
            <h1 style="margin:0;">Human-in-the-Loop Queue</h1>
        </div>
        <p>Review agent escalations. Approve to continue execution, reject to halt.</p>
    </div>
    """, unsafe_allow_html=True)

    pending_data = _api("/hitl/queue") or {}
    pending      = pending_data.get("items", [])

    if not pending:
        st.markdown("""
        <div style="text-align:center;padding:3.5rem 2rem;">
            <div style="width:56px;height:56px;border-radius:16px;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.2);display:flex;align-items:center;justify-content:center;font-size:1.6rem;margin:0 auto 1rem;">✅</div>
            <div style="font-size:1rem;font-weight:600;color:#10b981;">Queue is clear</div>
            <div style="font-size:0.85rem;color:#334155;margin-top:0.4rem;">No pending escalations.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background:rgba(245,158,11,0.07);border:1px solid rgba(245,158,11,0.2);border-radius:10px;padding:0.8rem 1.1rem;margin-bottom:1.4rem;display:flex;align-items:center;gap:0.8rem;">
            <span style="font-size:1.1rem;">⚠️</span>
            <span style="color:#fbbf24;font-weight:600;">{len(pending)} item{'s' if len(pending)!=1 else ''} awaiting review</span>
            <span style="color:#334155;font-size:0.82rem;">— execution is paused until resolved</span>
        </div>
        """, unsafe_allow_html=True)

        for item in pending:
            esc      = item.get("escalation", {}) if "escalation" in item else item
            trigger  = esc.get("trigger", "unknown").replace("_", " ").title()
            level    = esc.get("level", "approve_action")
            context  = esc.get("context", {})
            task_id  = item.get("task_id", "")
            task_req = item.get("task_request", "")[:160]
            item_id  = item.get("id", "")

            lc = {"notify": "#60a5fa", "approve_action": "#fbbf24",
                  "approve_plan": "#f87171", "take_over": "#a78bfa"}.get(level, "#94a3b8")

            st.markdown(f"""
            <div class="hitl-card">
                <div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.9rem;">
                    <div style="width:36px;height:36px;border-radius:10px;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);display:flex;align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0;">🔔</div>
                    <div>
                        <div style="font-size:0.95rem;font-weight:700;color:#fbbf24;margin-bottom:0.15rem;">{trigger}</div>
                        <div style="font-size:0.78rem;color:#64748b;">
                            Task <code style="background:#0a0f1a;padding:0.1rem 0.4rem;border-radius:4px;font-size:0.75rem;color:#94a3b8;">{task_id}</code>
                            &nbsp;·&nbsp;
                            <span style="color:{lc};font-weight:600;text-transform:uppercase;letter-spacing:0.04em;font-size:0.7rem;">{level}</span>
                        </div>
                    </div>
                </div>
                <div style="font-size:0.85rem;color:#64748b;padding:0.65rem 0.9rem;background:#080c14;border-radius:8px;border-left:2px solid #1e2b3c;line-height:1.5;">
                    {task_req}
                </div>
            </div>
            """, unsafe_allow_html=True)

            col_ctx, col_chat = st.columns(2)
            with col_ctx:
                with st.expander("📋 Full Context"):
                    st.json(context)
            with col_chat:
                st.markdown("**💬 Clarification Chat**")
                messages = (_api(f"/hitl/chat/{item_id}") or {}).get("messages", [])
                if not messages:
                    st.caption("No messages yet.")
                for m in messages:
                    role_label = "🧑 You" if m["role"] == "human" else "🤖 Agent"
                    role_color = "#60a5fa" if m["role"] == "human" else "#10b981"
                    st.markdown(
                        f'<div style="margin-bottom:0.5rem;padding:0.5rem 0.75rem;background:#080c14;'
                        f'border-left:2px solid {role_color};border-radius:0 8px 8px 0;font-size:0.84rem;">'
                        f'<span style="color:{role_color};font-weight:600;font-size:0.72rem;">{role_label}</span><br>'
                        f'<span style="color:#94a3b8;">{m["message"]}</span></div>',
                        unsafe_allow_html=True,
                    )
                chat_input = st.text_input("Ask a question:", key=f"chat_input_{item_id}",
                                           placeholder="e.g. What data sources did you use?")
                if st.button("Send", key=f"chat_send_{item_id}", use_container_width=True):
                    if chat_input.strip():
                        _api(f"/hitl/chat/{item_id}", method="POST",
                             json={"role": "human", "message": chat_input.strip()})
                        st.rerun()

            response = st.text_area("Guidance for agent:", key=f"resp_{item_id}",
                                     placeholder="Optional — tell the agent what to do next…")
            modified = st.text_area("Override output (optional):", key=f"mod_{item_id}",
                                     placeholder="Paste a corrected output to override the agent's result…")

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

    st.markdown('<div class="section-heading" style="margin-top:1.5rem;">Resolved History</div>', unsafe_allow_html=True)
    resolved = (_api("/hitl/resolved") or {}).get("items", [])
    if not resolved:
        st.markdown('<div style="color:#334155;font-size:0.85rem;padding:0.5rem 0;">No resolved items yet.</div>', unsafe_allow_html=True)
    else:
        for item in resolved[:8]:
            is_approved = item.get("status") == "approved"
            esc         = item.get("escalation", item)
            trigger     = esc.get("trigger","unknown").replace("_"," ").title() if isinstance(esc, dict) else str(esc)
            icon        = "✅" if is_approved else "❌"
            color       = "#10b981" if is_approved else "#ef4444"
            ts          = str(item.get("resolved_at") or item.get("created_at",""))[:16]
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:0.7rem;padding:0.6rem 0.9rem;background:#0f1623;border:1px solid #1e2b3c;border-radius:9px;margin-bottom:0.35rem;font-size:0.83rem;">
                <span>{icon}</span>
                <code style="color:#64748b;font-size:0.75rem;">{item.get('task_id','')}</code>
                <span style="color:#94a3b8;">{trigger}</span>
                <span style="color:#334155;margin-left:auto;font-family:monospace;font-size:0.75rem;">{ts}</span>
            </div>
            """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE: TRACE EXPLORER
# ════════════════════════════════════════════════════════════════════════
elif page == "Trace Explorer":
    st.markdown("""
    <div class="page-hero">
        <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.5rem;">
            <span style="font-size:1.5rem;">🔭</span>
            <h1 style="margin:0;">Trace Explorer</h1>
        </div>
        <p>Full decision log — every agent action, tool call, and routing decision, in order.</p>
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
        selected_id    = task_options[selected_label]
        full           = _api(f"/tasks/{selected_id}") or {}
        trace          = (_api(f"/tasks/{selected_id}/trace") or {}).get("trace", [])

        if full:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.markdown(metric_card("Status",     full.get("status","—").upper(),         accent="#3b82f6"), unsafe_allow_html=True)
            c2.markdown(metric_card("Tokens",     f"{full.get('total_tokens',0):,}",      accent="#8b5cf6"), unsafe_allow_html=True)
            c3.markdown(metric_card("Tool Calls", str(full.get("total_tool_calls",0)),    accent="#10b981"), unsafe_allow_html=True)
            c4.markdown(metric_card("Score",      f"{full.get('reviewer_score',0):.2f}",  accent="#f59e0b"), unsafe_allow_html=True)
            c5.markdown(metric_card("Cost",       f"${full.get('cost_usd',0):.4f}",       accent="#38bdf8"), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        # Step-through replay
        checkpoints = (_api(f"/tasks/{selected_id}/checkpoints") or {}).get("checkpoints", [])
        if checkpoints:
            st.markdown('<div class="section-heading">Step-Through Replay</div>', unsafe_allow_html=True)
            step = st.slider("Execution step", 0, len(checkpoints)-1, 0,
                             format="Step %d", key=f"replay_slider_{selected_id}")
            cp   = checkpoints[step]
            step_color = AGENT_HEX.get(cp.get("agent",""), "#64748b")
            st.markdown(f"""
            <div class="card" style="border-left:3px solid {step_color};">
                <div style="font-size:0.7rem;color:{step_color};font-weight:700;text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.5rem;">
                    Step {step} · {cp.get('agent','').title()}
                </div>
                <div style="font-size:1rem;font-weight:700;color:#f0f6ff;margin-bottom:0.6rem;">{cp.get('label','')}</div>
                <div style="font-size:0.8rem;color:#64748b;font-family:'JetBrains Mono',monospace;">{json.dumps(cp.get('detail',{}), indent=2)[:300]}</div>
            </div>
            """, unsafe_allow_html=True)
            if cp.get("snapshot"):
                with st.expander("📸 State snapshot"):
                    st.json(cp["snapshot"])

            st.markdown("<br>", unsafe_allow_html=True)
            col_rp1, col_rp2 = st.columns([3, 1])
            with col_rp1:
                modified_req = st.text_input(
                    "Replay with modified request (optional):", value="",
                    key=f"replay_req_{selected_id}",
                    placeholder="Leave blank to replay with original request",
                )
            with col_rp2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("▶ Replay", key=f"do_replay_{selected_id}", use_container_width=True):
                    result = _api(f"/tasks/{selected_id}/replay", method="POST",
                                  json={"modified_request": modified_req})
                    if result:
                        st.success(f"New task: `{result.get('replay_task_id')}` — check Task Monitor")
                    else:
                        st.error("Replay failed.")
            st.markdown("<hr>", unsafe_allow_html=True)

        # Timeline
        if not trace:
            st.markdown('<div style="color:#334155;text-align:center;padding:3rem;">No trace events recorded yet.</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="font-size:0.8rem;color:#64748b;margin-bottom:1rem;">{len(trace)} events recorded</div>',
                        unsafe_allow_html=True)
            st.markdown('<div class="timeline">', unsafe_allow_html=True)
            for event in trace:
                agent      = event.get("agent", "system")
                action     = event.get("action", "")
                detail     = event.get("detail")
                ts_str     = time.strftime("%H:%M:%S", time.localtime(event.get("ts", 0)))
                color_cls  = AGENT_COLORS.get(agent, "ac-system")
                hex_color  = AGENT_HEX.get(agent, "#334155")
                icon       = AGENT_ICONS.get(agent, "⚙️")

                detail_str = ""
                if detail:
                    if isinstance(detail, dict):
                        detail_str = "  ·  ".join(f"{k}: <b style='color:#94a3b8'>{v}</b>" for k, v in list(detail.items())[:3])
                    else:
                        detail_str = str(detail)[:120]

                st.markdown(f"""
                <div class="timeline-event">
                    <div class="timeline-dot {color_cls}" style="color:{hex_color};"></div>
                    <div class="timeline-content">
                        <div class="timeline-header">
                            <span class="timeline-agent {color_cls}">{icon} {agent}</span>
                            <span class="timeline-time">{ts_str}</span>
                        </div>
                        <div class="timeline-action">{action.replace("_"," ")}</div>
                        {f'<div style="font-size:0.75rem;color:#334155;margin-top:0.35rem;line-height:1.5;">{detail_str}</div>' if detail_str else ''}
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
    <div class="page-hero">
        <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.5rem;">
            <span style="font-size:1.5rem;">🧠</span>
            <h1 style="margin:0;">Memory & Tools</h1>
        </div>
        <p>Semantic long-term memory stored in Supabase pgvector, and live tool performance metrics.</p>
    </div>
    """, unsafe_allow_html=True)

    stats = _api("/memory/stats") or {}
    logs  = (_api("/tools/logs") or {}).get("logs", [])

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown('<div class="section-heading">Long-Term Memory</div>', unsafe_allow_html=True)
        mem_count  = stats.get("long_term_memories", 0)
        sb_enabled = stats.get("supabase_enabled", False)

        st.markdown(f"""
        <div class="card card-purple" style="display:flex;align-items:center;gap:1.4rem;padding:1.5rem;">
            <div style="width:52px;height:52px;border-radius:14px;background:rgba(139,92,246,0.12);border:1px solid rgba(139,92,246,0.2);display:flex;align-items:center;justify-content:center;font-size:1.6rem;flex-shrink:0;">🧠</div>
            <div>
                <div style="font-size:2.2rem;font-weight:800;color:#a78bfa;font-family:'JetBrains Mono',monospace;letter-spacing:-0.02em;">{mem_count}</div>
                <div style="font-size:0.8rem;color:#64748b;margin-top:0.1rem;">embeddings in Supabase pgvector</div>
                <div style="font-size:0.72rem;margin-top:0.35rem;">
                    <span style="color:{'#10b981' if sb_enabled else '#334155'};font-weight:600;">{'● Supabase connected' if sb_enabled else '○ Supabase offline'}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="font-size:0.82rem;color:#334155;line-height:1.7;padding:0.2rem 0.2rem 0.8rem;">
            After each task, the supervisor embeds a summary using
            <b style="color:#64748b">OpenAI text-embedding-3-small</b> and stores it in
            Supabase. Future tasks query this store via cosine similarity before planning —
            so the system gets smarter over time. Memories decay over 30 days.
        </div>
        """, unsafe_allow_html=True)

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            if st.button("🔄 Consolidate", use_container_width=True):
                r = _api("/memory/consolidate", method="POST")
                if r:
                    st.success(f"Merged {r.get('merged_removed',0)} dupes. {r.get('remaining',0)} remain.")
        with col_m2:
            if st.button("🗑️ Prune (90d)", use_container_width=True):
                r = _api("/memory/prune", method="POST")
                if r:
                    st.success(f"Pruned {r.get('pruned',0)} old memories.")

        st.markdown('<div class="section-heading" style="margin-top:1rem;">Recent Memories</div>', unsafe_allow_html=True)
        mem_list = (_api("/memory/list?limit=8") or {}).get("memories", [])
        if not mem_list:
            st.markdown('<div style="color:#334155;font-size:0.84rem;padding:0.5rem 0;">No memories yet — run a task to populate.</div>',
                        unsafe_allow_html=True)
        for m in mem_list:
            meta  = m.get("metadata", {})
            imp   = float(meta.get("importance", 0.5))
            ic    = "#10b981" if imp >= 0.7 else "#f59e0b" if imp >= 0.4 else "#334155"
            with st.expander(f"📌 {m['content'][:75]}…"):
                st.markdown(
                    f'<div style="font-size:0.78rem;color:#64748b;margin-bottom:0.5rem;">'
                    f'Importance: <span style="color:{ic};font-weight:600;">{imp:.2f}</span>'
                    f'&nbsp;·&nbsp; Task: <code style="font-size:0.75rem;">{meta.get("task_id","—")}</code>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.caption(m["content"])
                if st.button(f"Delete {m['id'][:8]}", key=f"del_{m['id']}"):
                    _api(f"/memory/{m['id']}", method="DELETE")
                    st.rerun()

    with col_r:
        st.markdown('<div class="section-heading">Tool Performance</div>', unsafe_allow_html=True)
        if not logs:
            st.markdown('<div style="color:#334155;padding:3rem;text-align:center;font-size:0.875rem;">No tool calls recorded yet.</div>',
                        unsafe_allow_html=True)
        else:
            total_calls    = len(logs)
            success_count  = sum(1 for l in logs if l.get("success"))
            avg_latency    = sum(l.get("latency_s", 0) for l in logs) / max(total_calls, 1)

            mc1, mc2, mc3 = st.columns(3)
            mc1.markdown(metric_card("Total Calls",   str(total_calls),                       accent="#3b82f6"), unsafe_allow_html=True)
            mc2.markdown(metric_card("Success Rate",  f"{100*success_count//max(total_calls,1)}%", accent="#10b981"), unsafe_allow_html=True)
            mc3.markdown(metric_card("Avg Latency",   f"{avg_latency:.2f}s",                  accent="#f59e0b"), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            for log_entry in reversed(logs[-12:]):
                success = log_entry.get("success", False)
                color   = "#10b981" if success else "#ef4444"
                tool    = log_entry.get("tool_name", log_entry.get("tool",""))
                agent   = log_entry.get("agent","")
                latency = log_entry.get("latency_s", 0)
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:0.7rem;padding:0.55rem 0.9rem;background:#0f1623;border:1px solid #1e2b3c;border-radius:8px;margin-bottom:0.3rem;font-size:0.81rem;">
                    <span style="color:{color};font-weight:700;font-size:0.8rem;">{'✓' if success else '✗'}</span>
                    <span style="color:#e2e8f0;font-weight:600;min-width:110px;">{tool}</span>
                    <span style="color:#1e2b3c;">›</span>
                    <span style="color:#64748b;">{agent}</span>
                    <span style="color:#334155;margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:0.75rem;">{latency:.3f}s</span>
                </div>
                """, unsafe_allow_html=True)

        if logs:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<div class="section-heading">Usage by Tool</div>', unsafe_allow_html=True)
            try:
                import pandas as pd
                import plotly.express as px

                tool_counts: dict = {}
                for l in logs:
                    t = l.get("tool_name", l.get("tool","unknown"))
                    tool_counts[t] = tool_counts.get(t, 0) + 1

                df  = pd.DataFrame(list(tool_counts.items()), columns=["Tool", "Calls"])
                fig = px.bar(
                    df.sort_values("Calls", ascending=True),
                    x="Calls", y="Tool", orientation="h",
                    color="Calls",
                    color_continuous_scale=["#0f1f3d", "#3b82f6"],
                )
                fig.update_layout(
                    plot_bgcolor="#080c14", paper_bgcolor="#080c14",
                    font_color="#64748b", showlegend=False,
                    coloraxis_showscale=False,
                    margin=dict(l=0, r=0, t=8, b=0),
                    xaxis=dict(gridcolor="#1e2b3c", zeroline=False),
                    yaxis=dict(gridcolor="rgba(0,0,0,0)"),
                    height=200,
                )
                fig.update_traces(marker_line_width=0, marker_corner_radius=4)
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                pass


# ════════════════════════════════════════════════════════════════════════
# PAGE: ANALYTICS
# ════════════════════════════════════════════════════════════════════════
elif page == "Analytics":
    st.markdown("""
    <div class="page-hero">
        <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.5rem;">
            <span style="font-size:1.5rem;">📈</span>
            <h1 style="margin:0;">Analytics</h1>
        </div>
        <p>Aggregate cost, model usage, escalation rates, and tool patterns across all tasks.</p>
    </div>
    """, unsafe_allow_html=True)

    agg = _api("/stats/aggregate") or {}

    if agg.get("total_tasks", 0) == 0:
        st.info("No tasks completed yet. Run some tasks to see analytics.")
    else:
        # KPIs
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.markdown(metric_card("Total Tasks",      str(agg["total_tasks"]),                   accent="#3b82f6"), unsafe_allow_html=True)
        k2.markdown(metric_card("Completed",         str(agg["completed_tasks"]),               accent="#10b981"), unsafe_allow_html=True)
        k3.markdown(metric_card("Total Cost",        f"${agg['total_cost_usd']:.4f}",           accent="#8b5cf6"), unsafe_allow_html=True)
        k4.markdown(metric_card("Avg Cost / Task",   f"${agg['avg_cost_usd']:.4f}",             accent="#f59e0b"), unsafe_allow_html=True)
        k5.markdown(metric_card("Escalation Rate",   f"{agg['escalation_rate']*100:.1f}%",      accent="#ef4444"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown('<div class="section-heading">Model Usage (tokens)</div>', unsafe_allow_html=True)
            model_usage = agg.get("model_usage", {})
            if model_usage:
                try:
                    import pandas as pd
                    import plotly.express as px

                    df_m  = pd.DataFrame([{"Model": m, "Tokens": t} for m, t in model_usage.items()])
                    fig_m = px.pie(
                        df_m, names="Model", values="Tokens",
                        color_discrete_sequence=["#3b82f6", "#10b981", "#a78bfa", "#f59e0b"],
                        hole=0.55,
                    )
                    fig_m.update_layout(
                        plot_bgcolor="#080c14", paper_bgcolor="#0f1623",
                        font_color="#64748b", showlegend=True,
                        legend=dict(font=dict(color="#64748b", size=11)),
                        margin=dict(l=0, r=0, t=10, b=0),
                        height=240,
                    )
                    fig_m.update_traces(textfont_color="#e2e8f0", textfont_size=11)
                    st.plotly_chart(fig_m, use_container_width=True)

                    from agents.base import MODEL_COST_PER_1K
                    for model, tokens in model_usage.items():
                        rate = MODEL_COST_PER_1K.get(model, 0.010)
                        cost = tokens * rate / 1000
                        st.markdown(
                            f'<div style="display:flex;justify-content:space-between;align-items:center;font-size:0.81rem;padding:0.35rem 0.5rem;border-bottom:1px solid #1e2b3c;">'
                            f'<span style="color:#64748b;">{model}</span>'
                            f'<span style="color:#e2e8f0;font-family:monospace;">{tokens:,} tok'
                            f'<span style="color:#334155;"> ≈ </span>${cost:.4f}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                except ImportError:
                    for m, t in model_usage.items():
                        st.write(f"{m}: {t:,} tokens")
            else:
                st.caption("No model usage data yet.")

        with col_b:
            st.markdown('<div class="section-heading">Tool Usage Patterns</div>', unsafe_allow_html=True)
            tool_usage = agg.get("tool_usage", {})
            if tool_usage:
                try:
                    import pandas as pd
                    import plotly.express as px

                    df_t  = pd.DataFrame([{"Tool": t, "Calls": c} for t, c in tool_usage.items()]).sort_values("Calls", ascending=True)
                    fig_t = px.bar(
                        df_t, x="Calls", y="Tool", orientation="h",
                        color="Calls",
                        color_continuous_scale=["#0a1f14", "#10b981"],
                    )
                    fig_t.update_layout(
                        plot_bgcolor="#080c14", paper_bgcolor="#0f1623",
                        font_color="#64748b", showlegend=False,
                        coloraxis_showscale=False,
                        margin=dict(l=0, r=0, t=8, b=0),
                        xaxis=dict(gridcolor="#1e2b3c", zeroline=False),
                        yaxis=dict(gridcolor="rgba(0,0,0,0)"),
                        height=240,
                    )
                    fig_t.update_traces(marker_line_width=0, marker_corner_radius=4)
                    st.plotly_chart(fig_t, use_container_width=True)
                except ImportError:
                    for t, c in tool_usage.items():
                        st.write(f"{t}: {c} calls")
            else:
                st.caption("No tool usage data yet.")

        # Performance summary (fixed - was rendering as literal ####)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-heading">Performance Summary</div>', unsafe_allow_html=True)
        p1, p2, p3, p4 = st.columns(4)
        p1.markdown(metric_card("Avg Tokens / Task",  f"{agg['avg_tokens']:,}",             accent="#8b5cf6"), unsafe_allow_html=True)
        p2.markdown(metric_card("Avg Review Score",   f"{agg['avg_reviewer_score']:.2f}",   accent="#10b981"), unsafe_allow_html=True)
        p3.markdown(metric_card("Avg Wall Time",      f"{agg['avg_wall_time_s']:.1f}s",     accent="#3b82f6"), unsafe_allow_html=True)
        p4.markdown(metric_card("Failed Tasks",       str(agg["failed_tasks"]),             accent="#ef4444"), unsafe_allow_html=True)

        if agg["escalated_tasks"] > 0:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class="card card-yellow" style="display:flex;align-items:center;gap:0.8rem;">
                <span style="font-size:1.1rem;">⚠️</span>
                <span style="color:#fbbf24;font-weight:600;">{agg['escalated_tasks']} task(s)</span>
                <span style="color:#64748b;font-size:0.875rem;">required human review
                &nbsp;·&nbsp; {agg['escalation_rate']*100:.1f}% escalation rate</span>
            </div>
            """, unsafe_allow_html=True)
