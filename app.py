from __future__ import annotations

import pandas as pd
import streamlit as st

from src.market_intel.config import get_settings
from src.market_intel.graph import MarketAnalysisGraph
from src.market_intel.ingestion import read_uploaded_file, read_url
from src.market_intel.logging_utils import configure_logging


settings = get_settings()
configure_logging()
app_cfg = settings.section("app")
ui_cfg = settings.section("ui")
conversation_cfg = settings.section("conversation")
output_cfg = settings.section("output")
credentials_cfg = settings.section("credentials")

st.set_page_config(
    page_title=app_cfg["page_title"],
    page_icon=app_cfg["page_icon"],
    layout="wide",
)


@st.cache_resource
def get_graph() -> MarketAnalysisGraph:
    return MarketAnalysisGraph()


def tokens_ready() -> bool:
    """Return True when both configured runtime credentials are present."""
    return settings.tokens_ready()


def apply_sidebar_tokens(openrouter_token: str, hf_token: str) -> None:
    """Apply sidebar credentials to this Streamlit process only.

    Values are intentionally not written back to .env or displayed in the UI.
    Clearing the cached graph ensures a previously-created OpenRouter client is
    rebuilt with the newly supplied token.
    """
    settings.set_runtime_tokens(
        openrouter_api_key=openrouter_token,
        hf_token=hf_token,
    )
    get_graph.clear()


def init_state() -> None:
    defaults = {
        "source_text": "",
        "source_name": "",
        "source_type": "",
        "source_size": 0,
        "cached_event": None,
        "previous_selected_companies": [],
        "messages": [],
        "flash_error": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_source_and_chat() -> None:
    st.session_state.source_text = ""
    st.session_state.source_name = ""
    st.session_state.source_type = ""
    st.session_state.source_size = 0
    st.session_state.cached_event = None
    st.session_state.previous_selected_companies = []
    st.session_state.messages = []
    st.session_state.flash_error = ""


def run_chat_turn(query: str, *, add_user_message: bool = True) -> None:
    if add_user_message:
        st.session_state.messages.append({"role": "user", "content": query})

    try:
        with st.spinner("Processing your question..."):
            result = get_graph().analyze(
                source_text=st.session_state.source_text,
                source_name=st.session_state.source_name,
                source_type=st.session_state.source_type,
                user_query=query,
                cached_event=st.session_state.cached_event,
                previous_selected_companies=st.session_state.previous_selected_companies,
            )

        # requested_companies contains only the explicitly selected company/company set.
        # An empty list means the user asked a general question, so all companies were scored.
        # Preserve the already-extracted event when a direct master-data lookup
        # returns no `event`. This keeps later impact follow-ups fast.
        if result.get("event") is not None:
            st.session_state.cached_event = result.get("event")
        st.session_state.previous_selected_companies = result.get(
            "requested_companies", []
        )
        st.session_state.messages.append(
            {
                "role": "assistant",
                "direct_answer": result.get("direct_answer"),
                "summary": result.get("response_summary", ""),
                "key_points": result.get("response_key_points", []),
                "impact_counts": result.get(
                    "response_impact_counts",
                    {"INCREASE": 0, "DECREASE": 0, "NEUTRAL": 0},
                ),
                "rows": result.get("response_rows", []),
                "evaluation": result.get("evaluation", {}),
                "input_guardrail": result.get("input_guardrail", {}),
                "output_guardrail": result.get("output_guardrail", {}),
                "log_folder": result.get("log_folder", ""),
            }
        )
        st.session_state.flash_error = ""
    except Exception as exc:
        st.session_state.flash_error = str(exc)


def _render_report_table(rows: list[dict], table_key: str) -> None:
    """Interactive table with native view/search/download/full-screen toolbar."""
    columns = output_cfg["table_columns"]
    df = pd.DataFrame(rows)
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    df = df[columns].copy()

    if "Confidence" in df.columns:
        df["Confidence"] = df["Confidence"].apply(
            lambda value: f"{float(value) * 100:.0f}%" if str(value).strip() else ""
        )
    if "Impact Score" in df.columns:
        df["Impact Score"] = df["Impact Score"].apply(
            lambda value: f"{float(value):+.4f}" if str(value).strip() else ""
        )

    # Color-code the Investment Suggestion while keeping it bold:
    # - negative/caution -> red
    # - positive -> green
    # - neutral -> default text color
    def style_investment_suggestion(value: object) -> str:
        text = str(value).upper()
        if "NEGATIVE" in text or "CAUTION" in text:
            return "color: #ff4b4b; font-weight: bold;"
        if "POSITIVE" in text:
            return "color: #00c853; font-weight: bold;"
        return "font-weight: bold;"

    # st.dataframe still supplies the native toolbar: column view, search,
    # download and full-screen/expand.
    styled = df.style.map(
        style_investment_suggestion,
        subset=["Investment Suggestion"],
    )

    column_config = {
        "Ticker / Code": st.column_config.TextColumn("Ticker / Code", width="small"),
        "Company Name": st.column_config.TextColumn("Company Name", width="medium"),
        "Impact Direction": st.column_config.TextColumn("Impact Direction", width="small"),
        "Investment Suggestion": st.column_config.TextColumn("Investment Suggestion", width="medium"),
        "Impact Score": st.column_config.TextColumn("Impact Score", width="small"),
        "Confidence": st.column_config.TextColumn("Confidence", width="small"),
        "Company Impacted Product": st.column_config.TextColumn(
            "Company Impacted Product", width=ui_cfg.get("key_points_column_width", "large")
        ),
        "Reason Behind Impact": st.column_config.TextColumn(
            "Reason Behind Impact", width=ui_cfg.get("reason_column_width", "large")
        ),
    }

    # Size the grid to the actual number of records. A fixed 560px height made
    # one-row results look like they contained many blank records.
    row_count = max(1, len(df))
    row_height = int(ui_cfg.get("table_row_height", 42))
    header_height = int(ui_cfg.get("table_header_height", 42))
    min_height = int(ui_cfg.get("table_min_height", 90))
    max_height = int(ui_cfg.get("table_max_height", 560))
    dynamic_height = min(
        max_height,
        max(min_height, header_height + (row_count * row_height) + 8),
    )

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=dynamic_height,
        column_config=column_config,
    )
    st.caption(
        "Use the table toolbar for View columns, Search, Download and Full screen / Expand."
    )

    # Explicit CSV download is retained so download is always visible even if the
    # Streamlit toolbar is collapsed on a smaller browser window.
    st.download_button(
        "Download table CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"market_impact_{table_key}.csv",
        mime="text/csv",
        key=f"download_{table_key}",
    )


def render_assistant_message(message: dict, message_index: int) -> None:
    # Direct table lookup: show only the requested value(s), nothing else.
    # Example: "What products are configured for Tesla, Inc.?" ->
    # "Electric vehicles, Megapack and stationary battery storage"
    if message.get("direct_answer") is not None:
        st.write(message["direct_answer"])
        return

    summary = message.get("summary", "")
    key_points = message.get("key_points", [])
    counts = message.get(
        "impact_counts", {"INCREASE": 0, "DECREASE": 0, "NEUTRAL": 0}
    )
    rows = message.get("rows", [])

    st.markdown("#### 1. News Summary")
    st.write(summary or "No summary was generated.")

    st.markdown("#### 2. Key Points")
    if key_points:
        for point in key_points:
            st.markdown(f"- {point}")
    else:
        st.markdown("- No additional key market point was extracted.")

    st.markdown("#### 3. Impact Score Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("INCREASE", int(counts.get("INCREASE", 0)))
    c2.metric("DECREASE", int(counts.get("DECREASE", 0)))
    c3.metric("NEUTRAL", int(counts.get("NEUTRAL", 0)))

    st.markdown("#### 4. Report Table")
    if rows:
        _render_report_table(rows, table_key=f"response_{message_index}")
    else:
        st.info("No company record matched this question.")


def load_source(mode: str, url_value: str, uploaded_file) -> bool:
    """Load the source only. Analysis starts from the user's chatbot question."""
    try:
        if mode == "File upload":
            if uploaded_file is None:
                raise ValueError(conversation_cfg["missing_news_message"])
            file_bytes = uploaded_file.getvalue()
            max_bytes = int(ui_cfg["max_upload_mb"]) * 1024 * 1024
            if len(file_bytes) > max_bytes:
                raise ValueError(
                    f'Uploaded file exceeds the configured {ui_cfg["max_upload_mb"]} MB limit.'
                )
            text, source_name = read_uploaded_file(uploaded_file.name, file_bytes)
            source_type = "file"
            source_size = len(file_bytes)
        else:
            if not url_value.strip():
                raise ValueError(conversation_cfg["missing_news_message"])
            text, source_name = read_url(url_value.strip())
            source_type = "url"
            source_size = len(text.encode("utf-8", errors="replace"))

        # Store parsed text and metadata only; never persist raw file bytes in session/result JSON.
        st.session_state.source_text = text
        st.session_state.source_name = source_name
        st.session_state.source_type = source_type
        st.session_state.source_size = source_size
        st.session_state.cached_event = None
        st.session_state.previous_selected_companies = []
        st.session_state.messages = []
        st.session_state.flash_error = ""
        return True
    except Exception as exc:
        st.session_state.flash_error = str(exc)
        return False


init_state()

st.title(f'{app_cfg["page_icon"]} {app_cfg["name"]}')
st.caption(app_cfg["disclaimer"])

with st.sidebar:
    st.header(credentials_cfg["sidebar_title"])

    current_openrouter_token = settings.openrouter_api_key
    current_hf_token = settings.hf_token

    openrouter_input = current_openrouter_token
    hf_input = current_hf_token

    if current_openrouter_token:
        st.caption(credentials_cfg["openrouter_configured_message"])
    else:
        openrouter_input = st.text_input(
            credentials_cfg["openrouter_label"],
            type="password",
            placeholder=credentials_cfg["openrouter_placeholder"],
            key="runtime_openrouter_token",
        )

    if current_hf_token:
        st.caption(credentials_cfg["hf_configured_message"])
    else:
        hf_input = st.text_input(
            credentials_cfg["hf_label"],
            type="password",
            placeholder=credentials_cfg["hf_placeholder"],
            key="runtime_hf_token",
        )

    # Only show Apply when at least one environment value is missing.
    if not (current_openrouter_token and current_hf_token):
        if st.button(
            credentials_cfg["apply_button"],
            use_container_width=True,
            key="apply_runtime_tokens",
        ):
            apply_sidebar_tokens(
                openrouter_token=(openrouter_input or "").strip(),
                hf_token=(hf_input or "").strip(),
            )
            st.rerun()

    if tokens_ready():
        st.success(credentials_cfg["success_message"])
    else:
        st.error(credentials_cfg["failure_message"])
        st.caption(credentials_cfg["missing_help_message"])

    st.caption(credentials_cfg["runtime_note"])
    st.divider()

    st.subheader("Company exposure data")
    try:
        exposure_engine = get_graph().exposure
        st.caption(
            f"{len(exposure_engine.source_file_names)} configured file(s) · "
            f"{len(exposure_engine.companies)} companies · "
            f"{len(exposure_engine.df)} exposure rows"
        )
        with st.expander("Loaded exposure files"):
            for source_file in exposure_engine.source_file_names:
                st.code(source_file, language=None)
    except Exception as exc:
        st.error(f"Exposure data could not be loaded: {exc}")

    st.divider()
    st.header("News input")
    source_mode = st.radio("Input source", ["File upload", "URL"], horizontal=True)
    uploaded = None
    url = ""
    if source_mode == "File upload":
        uploaded = st.file_uploader(
            "Upload related news",
            type=ui_cfg["supported_upload_extensions"],
        )
    else:
        url = st.text_input("Full news URL", placeholder="https://...")

    if st.button("Load news", type="primary", use_container_width=True):
        if load_source(source_mode, url, uploaded):
            st.success("News loaded. Ask your question in the chatbot.")

    if st.button("Clear source & conversation", use_container_width=True):
        clear_source_and_chat()

    st.divider()
    st.subheader("Current input source")
    if st.session_state.source_text:
        if st.session_state.source_type == "url":
            st.caption("URL")
            st.code(st.session_state.source_name, language=None)
        else:
            st.caption("Uploaded file")
            st.write(st.session_state.source_name)
            st.caption(f'{st.session_state.source_size:,} bytes loaded')
    else:
        st.warning(conversation_cfg["missing_news_message"])

st.subheader("Conversation")

if st.session_state.flash_error:
    st.error(st.session_state.flash_error)

if not st.session_state.messages:
    if st.session_state.source_text:
        st.info(
            "News is loaded. Ask about one company (for one record only) or ask a general question to analyze all configured companies."
        )
    else:
        st.info(
            "Attach a news file or URL from the sidebar, then ask your question. You can also select the source and send the first question without pressing Load news."
        )

for message_index, message in enumerate(st.session_state.messages, start=1):
    if message.get("role") == "user":
        with st.chat_message("user"):
            st.markdown(message.get("content", ""))
    else:
        with st.chat_message("assistant"):
            render_assistant_message(message, message_index)

query = st.chat_input(conversation_cfg["chat_placeholder"])
if query:
    # Table/master-data questions can be answered without attached news.
    # For market-impact questions, preserve the existing auto-load behavior.
    direct_preview, _ = get_graph().exposure.answer_table_question(
        query,
        previous_selected=st.session_state.previous_selected_companies,
    )
    if direct_preview is None and not tokens_ready():
        st.session_state.flash_error = credentials_cfg["analysis_blocked_message"]
        st.rerun()

    if direct_preview is None and not st.session_state.source_text:
        loaded = load_source(source_mode, url, uploaded)
        if not loaded:
            st.rerun()

    run_chat_turn(query, add_user_message=True)
    st.rerun()

with st.sidebar:
    st.divider()
    st.subheader("Response evaluation")
    assistant_messages = [
        m for m in st.session_state.messages if m.get("role") == "assistant"
    ]
    if not assistant_messages:
        st.caption("No response has been evaluated yet.")
    else:
        for idx, message in enumerate(assistant_messages, start=1):
            ev = message.get("evaluation", {})
            score = ev.get("overall_score", 0)
            passed = ev.get("passed", False)
            label = "PASS" if passed else "REVIEW"
            with st.expander(
                f"Response {idx}: {score}/100 · {label}",
                expanded=idx == len(assistant_messages),
            ):
                st.write(f'Judge: {ev.get("judge_mode", "unknown")}')
                st.write(f'Grounding: {ev.get("grounding", 0)}/5')
                st.write(f'Relevance: {ev.get("relevance", 0)}/5')
                st.write(f'Causal reasoning: {ev.get("causal_reasoning", 0)}/5')
                st.write(f'Format compliance: {ev.get("format_compliance", 0)}/5')
                st.write(f'Safety: {ev.get("safety", 0)}/5')
                st.write(
                    f'Uncertainty calibration: {ev.get("uncertainty_calibration", 0)}/5'
                )
                notes = ev.get("notes", [])
                if notes:
                    st.caption("Notes: " + " | ".join(map(str, notes)))
                warnings = message.get("input_guardrail", {}).get("warnings", [])
                if warnings:
                    st.warning("Guardrail: " + " | ".join(warnings))
