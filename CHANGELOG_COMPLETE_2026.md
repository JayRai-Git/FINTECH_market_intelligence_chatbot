# Complete 2026 Build — Change Summary

This build consolidates the previous chatbot updates into one project.

## Included

- LangGraph market-impact workflow.
- Streamlit conversational UI.
- File/URL news ingestion.
- Prompt-injection and SSRF guardrails.
- OpenRouter primary/fallback LLM flow.
- Optional Hugging Face local fallback support.
- Exact exposure matching + SentenceTransformer semantic fallback.
- Deterministic impact scoring.
- Company-specific 200–220 word reasoning.
- Four-section market report.
- Color-coded investment research suggestions.
- Dynamic table height and CSV export.
- Direct master-data/table Q&A.
- Global unique-list Q&A.
- Fuzzy company-name resolution.
- Conversational company follow-up memory.
- Cached extracted news event for faster follow-ups.
- Deterministic-first evaluation and optional LLM-as-Judge escalation.
- Per-run logging and JSON-safe serialization.
- Streamlit runtime token sidebar.
- Streamlit Community Cloud secret compatibility.
- GitHub Actions CI/CD and GitHub Pages showcase.
- 2026 real-world demo news and real-company exposure data.

## New in this build: multiple exposure files

`paths.company_exposure_csv` can now be either a string or a YAML list.

The loader supports CSV, XLSX and XLSM, validates each file, combines all rows, tracks the source filename and removes duplicate exposures by default.

Default configuration demonstrates the feature with two Excel workbooks.

## Validation

- Python compilation: passed.
- Pytest: 11 tests passed.
- Multi-file load validation: 2 Excel files, 20 exposure rows, 10 companies.
