"""Streamlit UI — Task submission, live status, HITL review, trace explorer."""
from __future__ import annotations
import time
import json
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import os
API = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Multi-Agent Orchestration System",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auto-refresh every 3s when a task is running ── #
if st.session_state.get("active_task"):
    st_autorefresh(interval=3000, key="poll")


# ── Sidebar navigation ── #
page = st.sidebar.radio(
    "Navigation",
    ["Submit Task", "Task Monitor", "HITL Review Queue", "Trace Explorer", "Memory & Tools"],
)

st.sidebar.divider()
try:
    r = requests.get(f"{API}/health", timeout=2)
    data = r.json()
    st.sidebar.success(f"API Online — {data['tasks_active']} task(s)")
    if data.get("supabase"):
        st.sidebar.info("🗄️ Supabase connected")
    else:
        st.sidebar.warning("⚠️ Supabase not connected\nTask history won't persist across restarts")
except Exception:
    st.sidebar.error("API Offline — start the backend first")

# ═══════════════════════════════════════════════════════════
if page == "Submit Task":
    st.title("Submit a Task")
    st.caption("The supervisor will decompose your request and dispatch specialized agents.")

    with st.form("task_form"):
        request = st.text_area(
            "Task description",
            height=120,
            placeholder="e.g. Research the latest advances in quantum computing, analyze the key players, and write an executive summary.",
        )
        user_id = st.text_input("User ID", value="demo_user")
        submitted = st.form_submit_button("Run Task", type="primary")

    if submitted and request.strip():
        try:
            resp = requests.post(f"{API}/tasks", json={"request": request, "user_id": user_id})
            data = resp.json()
            st.session_state["active_task"] = data["task_id"]
            st.success(f"Task started — ID: `{data['task_id']}`")
        except Exception as e:
            st.error(f"Failed to submit: {e}")

    if st.session_state.get("active_task"):
        task_id = st.session_state["active_task"]
        try:
            s = requests.get(f"{API}/tasks/{task_id}").json()
        except Exception:
            s = None

        if s:
            st.divider()
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Status", s["status"].upper())
            col2.metric("Subtasks", f"{s['completed']}/{s['total']}")
            col3.metric("Tokens", s["total_tokens"])
            col4.metric("Review Score", f"{s['reviewer_score']:.2f}" if s["reviewer_score"] else "—")

            if s["execution_plan"]:
                st.subheader("Execution Plan")
                for st_task in s["execution_plan"]:
                    icon = {"done": "✅", "in_progress": "⏳", "failed": "❌", "escalated": "🔔"}.get(st_task["status"], "⬜")
                    st.write(f"{icon} **[{st_task['specialist']}]** {st_task['description']}")

            if s["awaiting_human"]:
                st.warning("Paused — awaiting human review. Check the **HITL Review Queue**.")

            if s["final_output"]:
                st.subheader("Final Output")
                st.markdown(s["final_output"])
                if st.button("Clear / New Task"):
                    st.session_state.pop("active_task")
                    st.rerun()

            if s["errors"]:
                with st.expander("Errors"):
                    for e in s["errors"]:
                        st.code(e)

# ═══════════════════════════════════════════════════════════
elif page == "Task Monitor":
    st.title("All Tasks")
    try:
        tasks = requests.get(f"{API}/tasks").json()
    except Exception:
        tasks = []
        st.error("Cannot reach API")

    if not tasks:
        st.info("No tasks yet.")
    else:
        for t in reversed(tasks):
            status_color = {"done": "green", "failed": "red", "escalated": "orange"}.get(t["status"], "blue")
            with st.expander(f":{status_color}[{t['status'].upper()}] {t['request'][:80]}  — `{t['task_id']}`"):
                try:
                    full = requests.get(f"{API}/tasks/{t['task_id']}").json()
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Reviewer Score", f"{full['reviewer_score']:.2f}")
                    col2.metric("Tokens Used", full["total_tokens"])
                    col3.metric("Tool Calls", full["total_tool_calls"])
                    if full["final_output"]:
                        st.markdown(full["final_output"])
                except Exception:
                    pass

# ═══════════════════════════════════════════════════════════
elif page == "HITL Review Queue":
    st.title("Human-in-the-Loop Review Queue")
    st.caption("Review and approve/reject agent escalations before execution continues.")

    try:
        pending = requests.get(f"{API}/hitl/queue").json()["items"]
    except Exception:
        pending = []
        st.error("Cannot reach API")

    if not pending:
        st.success("No pending items.")
    else:
        for item in pending:
            esc = item["escalation"]
            with st.container(border=True):
                st.subheader(f"🔔 {esc['trigger'].replace('_', ' ').title()}")
                col1, col2 = st.columns(2)
                col1.write(f"**Level:** `{esc['level']}`")
                col2.write(f"**Task:** `{item['task_id']}`")
                st.write(f"**Request:** {item['task_request'][:200]}")

                with st.expander("Full Context"):
                    st.json(esc["context"])

                response = st.text_area("Response / guidance for agent:", key=f"resp_{item['id']}")
                modified = st.text_area("Modified output (optional — overrides agent output):", key=f"mod_{item['id']}")

                col_a, col_b = st.columns(2)
                if col_a.button("✅ Approve", key=f"approve_{item['id']}", type="primary"):
                    requests.post(f"{API}/hitl/resolve", json={
                        "item_id": item["id"], "approved": True,
                        "response": response, "modified_output": modified,
                    })
                    st.rerun()
                if col_b.button("❌ Reject", key=f"reject_{item['id']}"):
                    requests.post(f"{API}/hitl/resolve", json={
                        "item_id": item["id"], "approved": False, "response": response,
                    })
                    st.rerun()

    st.divider()
    st.subheader("Resolved Items")
    try:
        resolved = requests.get(f"{API}/hitl/resolved").json()["items"]
        for item in resolved[:10]:
            status_icon = "✅" if item.get("status") == "approved" else "❌"
            st.write(f"{status_icon} `{item['task_id']}` — {item['escalation']['trigger']} — {item.get('human_response', '')[:80]}")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════
elif page == "Trace Explorer":
    st.title("Trace Explorer")
    st.caption("Full decision log for every agent action.")

    try:
        tasks = requests.get(f"{API}/tasks").json()
    except Exception:
        tasks = []

    if not tasks:
        st.info("No tasks to explore yet.")
    else:
        task_options = {f"{t['task_id']} — {t['request'][:60]}": t["task_id"] for t in reversed(tasks)}
        selected_label = st.selectbox("Select task", list(task_options.keys()))
        selected_id = task_options[selected_label]

        try:
            trace = requests.get(f"{API}/tasks/{selected_id}/trace").json()["trace"]
            full = requests.get(f"{API}/tasks/{selected_id}").json()
        except Exception:
            trace, full = [], {}

        if full:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Status", full.get("status", "—").upper())
            col2.metric("Tokens", full.get("total_tokens", 0))
            col3.metric("Tool Calls", full.get("total_tool_calls", 0))
            col4.metric("Escalations", len(full.get("escalations", [])))

        st.subheader(f"Trace ({len(trace)} events)")
        for event in trace:
            agent_colors = {
                "supervisor": "blue", "research": "green", "analysis": "orange",
                "writing": "violet", "code": "red", "reviewer": "gray", "system": "gray",
            }
            color = agent_colors.get(event["agent"], "gray")
            ts = time.strftime("%H:%M:%S", time.localtime(event["ts"]))
            with st.expander(f":{color}[{event['agent'].upper()}] {event['action']}  — {ts}"):
                if event.get("detail"):
                    st.json(event["detail"])

# ═══════════════════════════════════════════════════════════
elif page == "Memory & Tools":
    st.title("Memory & Tool Analytics")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Long-Term Memory")
        try:
            stats = requests.get(f"{API}/memory/stats").json()
            st.metric("Stored memories", stats["long_term_memories"])
        except Exception:
            st.error("Cannot reach API")

    with col2:
        st.subheader("Tool Call Log")
        try:
            logs = requests.get(f"{API}/tools/logs").json()["logs"]
            if logs:
                import pandas as pd
                df = pd.DataFrame([
                    {
                        "tool": l["tool"],
                        "agent": l["agent"],
                        "success": "✅" if l["success"] else "❌",
                        "latency_s": l["latency_s"],
                    }
                    for l in reversed(logs[-20:])
                ])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No tool calls yet.")
        except Exception:
            st.error("Cannot reach API")
