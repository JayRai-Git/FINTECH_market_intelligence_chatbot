# AI Market Intelligence Chatbot — Complete 2026 Demo

A Streamlit + LangGraph market-intelligence application that converts news into structured market drivers, maps those drivers to real-company product/raw-material exposures, calculates deterministic directional impact signals, and supports conversational follow-ups and direct master-data questions.

> Research signal only. The application does not execute trades, guarantee future returns, or replace regulated investment advice.

## Main capabilities

- Upload news as PDF, DOCX, CSV, JSON, TXT or Markdown, or load a public HTTP/HTTPS URL.
- Input guardrails, prompt-injection checks and SSRF/private-network URL protection.
- OpenRouter LLM event extraction with primary/fallback model support.
- Exact exposure matching first; SentenceTransformer semantic matching only when exact matching is not sufficient.
- Deterministic company impact score using direction × sensitivity × exposure weight × event magnitude × confidence × similarity.
- Company-specific `INCREASE`, `DECREASE`, or `NEUTRAL` output.
- Investment-research labels: `POSITIVE WATCH`, `CAUTION / NEGATIVE WATCH`, `NEUTRAL / MONITOR`.
- Company-specific 200–220 word reason, impact score and confidence.
- Direct company-table questions without running the LLM/news workflow.
- Follow-up memory for questions such as `Why?`, `What is its ticker?`, or `What are its products?`.
- Deterministic-first quality evaluation with optional LLM-as-Judge escalation.
- Per-run trace logs.
- Streamlit runtime token entry when `.env`/cloud secrets are absent.
- GitHub Actions CI plus GitHub Pages client showcase.
- 2026 real-world demo news and real-company exposure examples.
- **Multiple CSV/XLSX exposure files can be configured and automatically combined.**

## Architecture

```text
News File / Public URL
        |
        v
Secure Ingestion
        |
        v
Input Guardrail
        |
        v
LLM Event Extraction
        |
        v
Company Selection / Follow-up Resolution
        |
        v
Exposure Engine
  | exact match first
  | semantic match fallback
        |
        v
Deterministic Impact Scoring
        |
        v
Response Builder
        |
        v
Output Guardrail
        |
        v
Deterministic Evaluation
        |
        +---- low-quality response ----> LLM-as-Judge
        |
        v
Streamlit Report + Logs
```

Direct master-data questions take a shorter route:

```text
Question -> Table-field detection -> Company resolution -> Combined exposure data -> Direct answer
```

## Multiple exposure files

The existing key `paths.company_exposure_csv` is backward compatible. It now accepts either one file:

```yaml
paths:
  company_exposure_csv: data/real_company_exposure_2026.csv
```

or multiple files:

```yaml
paths:
  company_exposure_csv:
    - data/company_exposure_2026_part1.xlsx
    - data/company_exposure_2026_part2.xlsx
```

Supported company exposure formats are:

- `.csv`
- `.xlsx`
- `.xlsm`

Every file must contain these columns:

```text
company
trading_name
ticker
industry
region
product
exposure_type
material_or_driver
usage_reason
sensitivity
exposure_weight
```

Extra columns are allowed. For Excel workbooks, the loader uses the configured `Company Exposure` sheet when available; otherwise it reads the first worksheet. All configured files are concatenated into one in-memory DataFrame. Duplicate exposure rows are removed when `exposure_data.deduplicate_rows: true`.

The sidebar shows the number and names of the exposure files that were successfully loaded.

## Included real-company demonstration data

The default configuration loads two Excel files containing 20 exposure records across:

- Albemarle Corporation (`ALB`)
- Tesla, Inc. (`TSLA`)
- NVIDIA Corporation (`NVDA`)
- Taiwan Semiconductor Manufacturing Company Limited / TSMC (`TSM`)
- Exxon Mobil Corporation (`XOM`)
- Delta Air Lines, Inc. (`DAL`)
- JPMorgan Chase & Co. (`JPM`)
- Visa Inc. (`V`)
- Nucor Corporation (`NUE`)
- Ford Motor Company (`F`)

Company identities, tickers, broad products and broad exposure relationships are based on public company information. `sensitivity` and `exposure_weight` are intentionally assigned demo-model parameters and are not company-reported forecasts.

## Included 2026 news scenarios

The folder `data/news/` contains five synthesized/paraphrased 2026 demonstration briefs with source references inside each file:

1. Lithium-price rebound and battery-storage demand.
2. AI-chip demand and export-control pressure.
3. Strait of Hormuz / oil-supply risk.
4. Federal Reserve rates, inflation and labor-market weakness.
5. U.S. steel/aluminum/copper derivative-tariff changes.

`UserQuestion_readme.me` contains four question/follow-up sets for every news scenario.

## Project structure

```text
ai_market_intelligence_chatbot_complete_2026/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── README_2026_demo_pack.md
├── UserQuestion_readme.me
├── GitHub_CICD_Connection_readme.me
├── readme_git.me
├── config/
│   ├── settings.yaml
│   └── prompts.yaml
├── data/
│   ├── company_exposure_2026_part1.xlsx
│   ├── company_exposure_2026_part2.xlsx
│   ├── real_company_exposure_2026.csv
│   ├── real_company_exposure_2026_reference.xlsx
│   ├── sample_company_exposure.csv
│   ├── sample_news.txt
│   └── news/
│       ├── news_01_lithium_rebound_and_storage_demand_2026.txt
│       ├── news_02_ai_chip_demand_and_export_controls_2026.txt
│       ├── news_03_hormuz_oil_supply_risk_2026.txt
│       ├── news_04_fed_rates_inflation_and_jobs_2026.txt
│       └── news_05_us_metal_tariff_adjustment_2026.txt
├── src/market_intel/
│   ├── config.py
│   ├── schemas.py
│   ├── security.py
│   ├── guardrails.py
│   ├── ingestion.py
│   ├── llm.py
│   ├── exposure.py
│   ├── response_builder.py
│   ├── evaluation.py
│   ├── logging_utils.py
│   └── graph.py
├── tests/
│   ├── conftest.py
│   ├── test_data_loading.py
│   ├── test_scoring.py
│   ├── test_security.py
│   └── test_serialization.py
├── .github/workflows/cicd.yml
└── docs/
    ├── index.html
    └── styles.css
```

## Local setup

Recommended Python: 3.11.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create `.env` from `.env.example`:

```env
OPENROUTER_API_KEY=your_openrouter_key
HF_TOKEN=your_huggingface_token
```

Then run:

```powershell
streamlit run app.py
```

If tokens are absent from `.env`, the latest UI can request the missing tokens in the sidebar and keeps them only in the current Python process.

## Streamlit Community Cloud

Do not commit real API keys. In `share.streamlit.io`:

1. Deploy the GitHub repository and choose `app.py`.
2. Open the app settings.
3. Open **Secrets**.
4. Add:

```toml
OPENROUTER_API_KEY = "your-openrouter-key"
HF_TOKEN = "your-huggingface-token"
```

5. Save/reboot the application if required.

The code reads the same names through environment variables, so no production secret needs to be stored in Git.

## Output format

A normal market-impact question produces exactly:

1. News Summary
2. Key Points
3. Impact Score Summary
4. Report Table

The report table contains:

```text
Ticker / Code
Company Name
Impact Direction
Investment Suggestion
Impact Score
Confidence
Company Impacted Product
Reason Behind Impact
```

Direct table questions return only the requested value(s).

## Impact formula

For each matched event-driver/exposure pair:

```text
raw contribution =
    direction multiplier
  × company sensitivity
  × exposure weight
  × event impact magnitude
  × event confidence
  × semantic/exact match strength
```

The company's contributions are summed and clipped to the configured range. Default thresholds are:

```text
score >= +0.15 -> UP -> INCREASE
score <= -0.15 -> DOWN -> DECREASE
otherwise      -> NEUTRAL
```

## Tests

```powershell
pytest -q
```

The included suite validates security behavior, serialization, multi-Excel loading, deterministic impact scoring, response shape, direct table Q&A, and follow-up company memory.

## Git push

```powershell
git status
git add .
git status
git commit -m "Update complete 2026 market intelligence chatbot"
git push origin main
```

Never commit `.env` or Streamlit secrets.
