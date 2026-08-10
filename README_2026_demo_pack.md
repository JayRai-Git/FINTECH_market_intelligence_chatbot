# 2026 Real-World Demo Pack

This project already contains five synthesized 2026 news briefs and a real-company exposure dataset for client demonstrations.

## Default multi-file setup

`config/settings.yaml` is already configured to load two Excel workbooks:

```yaml
paths:
  company_exposure_csv:
    - data/company_exposure_2026_part1.xlsx
    - data/company_exposure_2026_part2.xlsx
```

The application combines both workbooks into one in-memory exposure table.

A complete CSV (`data/real_company_exposure_2026.csv`) and a human-readable Excel reference (`data/real_company_exposure_2026_reference.xlsx`) are also included. They are not loaded by default, so they do not cause duplicate scoring.

## News files

Use the files under `data/news/`:

1. `news_01_lithium_rebound_and_storage_demand_2026.txt`
2. `news_02_ai_chip_demand_and_export_controls_2026.txt`
3. `news_03_hormuz_oil_supply_risk_2026.txt`
4. `news_04_fed_rates_inflation_and_jobs_2026.txt`
5. `news_05_us_metal_tariff_adjustment_2026.txt`

Each file is a synthesized/paraphrased demo brief and contains its public source references.

## Questions

Open `UserQuestion_readme.me`. It provides four question/follow-up sets for each news file, including:

- all-company analysis;
- single-company analysis;
- company comparison;
- follow-up memory;
- direct product/ticker/region/driver lookup.

## Modeling note

Company identities, tickers, broad product lines and broad exposure relationships are grounded in public company information. `sensitivity` and `exposure_weight` are manually assigned demonstration parameters for the deterministic scoring engine. They are not company-reported forecasts or investment recommendations.
