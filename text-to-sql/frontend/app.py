"""
app.py

Streamlit frontend for the Text-to-SQL system.
"""

import streamlit as st
import requests
import pandas as pd
from typing import Dict, Any, Optional

API_BASE_URL = 'http://localhost:8000'

# Page Configuration
st.set_page_config(
    page_title='Text-to-SQL',
    page_icon="🔍",
    layout='wide',
    initial_sidebar_state='expanded'
)

# Custom CSS
st.markdown("""
<style>
    .confidence-high {
        background-color: #1a3a1a;
        border: 2px solid #28a745;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        color: #90ee90;
    }
    .confidence-medium {
        background-color: #3a3000;
        border: 2px solid #ffc107;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        color: #ffd700;
    }
    .confidence-low {
        background-color: #3a0000;
        border: 2px solid #dc3545;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        color: #ff6b6b;
    }
    .metric-card {
        background-color: #1e1e2e;
        border: 1px solid #444;
        border-radius: 8px;
        padding: 12px;
        margin: 4px 0;
        color: #ffffff;
        line-height: 1.8;
    }
    .sql-box {
        background-color: #1e1e1e;
        color: #f8f8f2;
        border: 1px solid #444;
        border-radius: 8px;
        padding: 16px;
        font-family: monospace;
        font-size: 13px;
        white-space: pre-wrap;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# API Helper Functions
# ---------------------------------------------------------------------------

def call_api(endpoint: str, method: str = 'GET',
             data: Optional[Dict] = None) -> Optional[Dict]:
    """Makes HTTP requests to the FastAPI backend."""
    url = f'{API_BASE_URL}{endpoint}'
    try:
        if method == 'POST':
            response = requests.post(url, json=data, timeout=120)
        else:
            response = requests.get(url, timeout=120)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error(
            'Cannot connect to the API. '
            'Make sure FastAPI is running on port 8000. '
            'Run: uvicorn main:app --reload --port 8000'
        )
        return None
    except requests.exceptions.Timeout:
        st.error(
            'Request timed out. The pipeline is taking longer than expected.'
        )
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f'API error: {str(e)}')
        return None


def check_api_health() -> bool:
    """Checks if the FastAPI backend is running."""
    result = call_api('/health')
    return result is not None and result.get('status') == 'Healthy'


# ---------------------------------------------------------------------------
# UI Component Functions
# ---------------------------------------------------------------------------

def render_confidence_score(confidence: Dict[str, Any]):
    """Renders the confidence score section in the sidebar."""
    score = confidence.get('final_score', 0)
    label = confidence.get('confidence_label', 'UNKNOWN')
    recommendation = confidence.get('recommendation', '')
    signal_breakdown = confidence.get('signal_breakdown', {})
    failed_checks = confidence.get('failed_checks', [])

    css_class = {
        'HIGH': 'confidence-high',
        'MEDIUM': 'confidence-medium',
        'LOW': 'confidence-low'
    }.get(label, 'confidence-medium')

    emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(label, "⚪")

    st.markdown(f"""
    <div class="{css_class}">
        <strong>{emoji} Confidence: {label}</strong><br>
        Score: {score:.1%}<br>
        <small>{recommendation}</small>
    </div>
    """, unsafe_allow_html=True)

    if signal_breakdown:
        st.markdown('**Signal Breakdown:**')
        breakdown_data = []
        for signal_name, details in signal_breakdown.items():
            breakdown_data.append({
                "Signal": signal_name.replace("_", " ").title(),
                "Score": f"{details.get('raw_score', 0):.2f}",
                "Weight": f"{details.get('weight', 0):.0%}",
                "Contribution": f"{details.get('contribution', 0):.3f}"
            })
        st.dataframe(
            pd.DataFrame(breakdown_data),
            hide_index=True,
            use_container_width=True
        )

    if failed_checks:
        st.warning(f'⚠️ Failed checks: {", ".join(failed_checks)}')


def render_hallucination_details(hallucination: Dict[str, Any]):
    """Renders hallucination detection results in an expander."""
    with st.expander("🔬 Hallucination Detection Details"):

        # Back-translation
        back_trans = hallucination.get("back_translation", {})
        st.markdown("**Back-Translation Verification:**")
        st.write(
            f"Back-translated question: "
            f"*{back_trans.get('back_translated_question', 'N/A')}*"
        )
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Alignment Score",
            f"{back_trans.get('alignment_score', 0):.2f}"
        )
        col2.metric(
            "Keyword Overlap",
            f"{back_trans.get('keyword_overlap_score', 0):.2f}"
        )
        col3.metric(
            "Semantic Similarity",
            f"{back_trans.get('semantic_similarity_score', 0):.2f}"
        )

        if back_trans.get("is_hallucination"):
            st.error("⚠️ Potential hallucination detected in back-translation")

        st.divider()

        # Sanity check
        sanity = hallucination.get("sanity_check", {})
        st.markdown("**Result Sanity Checks:**")
        sanity_score = sanity.get("sanity_score", 1.0)
        failed = sanity.get("failed_checks", [])

        if sanity.get("all_passed"):
            st.success(
                f"✅ All sanity checks passed (score: {sanity_score:.1%})"
            )
        else:
            st.warning(
                f"⚠️ {len(failed)} sanity check(s) failed: "
                f"{', '.join(failed)}"
            )
            for warning in sanity.get("warnings", []):
                st.write(f"• {warning}")

        st.divider()

        # Multi-query validation
        multi = hallucination.get("multi_query", {})
        st.markdown("**Multi-Query Validation:**")

        if multi.get("agree"):
            st.success(
                f"✅ Two independent queries agree "
                f"(score: {multi.get('agreement_score', 0):.2f})"
            )
        else:
            st.warning(
                f"⚠️ Queries diverged "
                f"(score: {multi.get('agreement_score', 0):.2f})"
            )
        st.write(f"*{multi.get('explanation', '')}*")


def render_query_history(history: list):
    """Renders past queries in the sidebar."""
    if not history:
        st.info("No queries yet — ask your first question!")
        return

    for entry in history:
        label = entry.get("confidence_label", "")
        emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(label, "⚪")
        question = entry.get("question", "")[:40]

        with st.expander(f"{emoji} {question}..."):
            st.write(f"**Rows:** {entry.get('row_count', 0)}")
            st.write(
                f"**Confidence:** {entry.get('confidence_score', 0):.2f} "
                f"({label})"
            )
            st.write(f"**Time:** {entry.get('total_time_ms', 0):.0f}ms")
            st.write(f"**At:** {entry.get('timestamp', '')}")
            if entry.get("sql"):
                st.code(entry["sql"], language="sql")


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

def main():
    # Initialize session state
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "feedback_submitted" not in st.session_state:
        st.session_state.feedback_submitted = False

    # Header
    st.title("🔍 Text-to-SQL Query Interface")
    st.markdown(
        "Ask questions in plain English — get SQL queries and results "
        "with hallucination detection and confidence scoring."
    )

    # API Health Check
    if not check_api_health():
        st.error(
            "⚠️ FastAPI backend is not running. "
            "Start it with: `cd app && uvicorn main:app --reload --port 8000`"
        )
        st.stop()

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    with st.sidebar:
        st.header("📊 Query Details")

        if st.session_state.last_result:
            result = st.session_state.last_result
            if result.get("confidence"):
                render_confidence_score(result["confidence"])
            st.divider()
            st.markdown("**Query Metadata:**")
            st.markdown(
                f"<div class='metric-card'>"
                f"⏱️ Execution: {result.get('execution_time_ms', 0):.1f}ms<br>"
                f"📋 Rows: {result.get('row_count', 0)}<br>"
                f"🗂️ Tables: {', '.join(result.get('tables_used', []))}"
                f"</div>",
                unsafe_allow_html=True
            )
        else:
            st.info("Submit a question to see query details here.")

        st.divider()
        st.header("📜 Query History")
        history_data = call_api("/v1/history?limit=5")
        if history_data:
            render_query_history(history_data.get("history", []))

    # ------------------------------------------------------------------
    # Question Input
    # ------------------------------------------------------------------
    col1, col2 = st.columns([4, 1])

    with col1:
        question = st.text_input(
            "Ask a question about your data:",
            placeholder="e.g. Which customers have spent the most money?",
            key="question_input"
        )

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        submit = st.button(
            "Submit",
            type="primary",
            use_container_width=True
        )

    # ------------------------------------------------------------------
    # Process Question — only runs when Submit is clicked
    # ------------------------------------------------------------------
    if submit and question:
        st.session_state.feedback_submitted = False

        with st.spinner("Running pipeline..."):
            result = call_api(
                "/v1/query",
                method="POST",
                data={"question": question}
            )

        if result:
            st.session_state.last_result = result

    elif submit and not question:
        st.warning("Please enter a question first.")

    # ------------------------------------------------------------------
    # Display Results — runs on every page load if we have a stored result
    # This is OUTSIDE the submit block so feedback buttons persist
    # ------------------------------------------------------------------
    if st.session_state.last_result:
        result = st.session_state.last_result

        # Clarification needed
        if result.get("needs_clarification"):
            st.warning("⚠️ This question needs clarification:")
            st.write(result.get("message", ""))

            if result.get("interpretations"):
                st.markdown("**Please choose an interpretation:**")
                for i, interp in enumerate(result["interpretations"], 1):
                    if st.button(
                        f"{i}. {interp['label']}: {interp['description']}",
                        key=f"interp_{i}"
                    ):
                        with st.spinner("Running pipeline..."):
                            new_result = call_api(
                                "/v1/query",
                                method="POST",
                                data={"question": interp["refined_question"]}
                            )
                        if new_result:
                            st.session_state.last_result = new_result
                            st.rerun()

        # Query blocked
        elif not result.get("approved") and result.get("blocked_reason"):
            st.error(f"🚫 Query blocked: {result['blocked_reason']}")

        # Success
        elif result.get("success"):

            # Generated SQL
            st.markdown("### Generated SQL")
            st.markdown(
                f"<div class='sql-box'>{result.get('sql', '')}</div>",
                unsafe_allow_html=True
            )

            if result.get("explanation"):
                st.info(f"💡 {result['explanation']}")

            st.divider()

            # Results table
            st.markdown(
                f"### Results "
                f"<small>({result.get('row_count', 0)} rows)</small>",
                unsafe_allow_html=True
            )

            if result.get("data"):
                df = pd.DataFrame(result["data"])
                for col in df.columns:
                    if df[col].dtype == object:
                        try:
                            df[col] = df[col].astype(float)
                        except (ValueError, TypeError):
                            pass
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Query returned no results.")

            # Hallucination details
            if result.get("hallucination"):
                render_hallucination_details(result["hallucination"])

            st.divider()

            # Feedback section
            st.markdown("### Was this result correct?")
            col_yes, col_no, _ = st.columns([1, 1, 2])

            if not st.session_state.feedback_submitted:
                with col_yes:
                    if st.button("✅ Correct", use_container_width=True):
                        feedback_result = call_api(
                            "/v1/feedback",
                            method="POST",
                            data={
                                "query_id": result.get("query_id", ""),
                                "question": result.get(
                                    "question",
                                    st.session_state.get(
                                        "question_input", ""
                                    )
                                ),
                                "sql": result.get("sql", ""),
                                "is_correct": True
                            }
                        )
                        if feedback_result:
                            st.session_state.feedback_submitted = True
                            st.success("Thanks! Marked as correct ✅")
                            st.rerun()

                with col_no:
                    if st.button("❌ Wrong", use_container_width=True):
                        feedback_result = call_api(
                            "/v1/feedback",
                            method="POST",
                            data={
                                "query_id": result.get("query_id", ""),
                                "question": result.get(
                                    "question",
                                    st.session_state.get(
                                        "question_input", ""
                                    )
                                ),
                                "sql": result.get("sql", ""),
                                "is_correct": False
                            }
                        )
                        if feedback_result:
                            st.session_state.feedback_submitted = True
                            st.warning(
                                "Thanks! Marked as incorrect — "
                                "this becomes a test case ❌"
                            )
                            st.rerun()
            else:
                st.success("Feedback submitted!")

        # Execution failed
        else:
            st.error(
                f"❌ Query failed: {result.get('error', 'Unknown error')}"
            )

    # ------------------------------------------------------------------
    # Schema Reference
    # ------------------------------------------------------------------
    with st.expander("📖 Database Schema Reference"):
        schema_data = call_api("/v1/schema")
        if schema_data and schema_data.get("schema"):
            schema = schema_data["schema"]
            for table_name, table_info in schema.get("tables", {}).items():
                st.markdown(f"**{table_name}**")
                cols = [
                    f"`{c['name']}` ({c['type']})"
                    for c in table_info.get("columns", [])
                ]
                st.write(", ".join(cols))
                st.divider()


if __name__ == "__main__":
    main()