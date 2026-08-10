# Multiple Company Exposure Files

The same `paths.company_exposure_csv` setting now accepts one filename or a list of filenames.

## One CSV

```yaml
paths:
  company_exposure_csv: data/real_company_exposure_2026.csv
```

## Multiple Excel files

```yaml
paths:
  company_exposure_csv:
    - data/company_exposure_2026_part1.xlsx
    - data/company_exposure_2026_part2.xlsx
```

## Mixed CSV and Excel

```yaml
paths:
  company_exposure_csv:
    - data/company_exposure_us.csv
    - data/company_exposure_india.xlsx
    - data/company_exposure_europe.xlsx
```

The files are read in the configured order, concatenated, validated and optionally deduplicated.

## Excel worksheet

```yaml
exposure_data:
  excel_sheet_name: Company Exposure
  deduplicate_rows: true
```

If an Excel workbook contains a sheet named `Company Exposure`, that sheet is used. If it does not, the first sheet is used.

## Required columns in every file

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

Extra fields such as `source_url`, `parent_company` or `modeling_note` are allowed.

`sensitivity` and `exposure_weight` must contain numeric values. The application raises a clear startup error when a configured file does not exist, has an unsupported extension, misses a required column, or contains an invalid numeric model parameter.

After changing the configured files, restart Streamlit. In Streamlit Community Cloud, push the new files and `config/settings.yaml` to GitHub; the app will reload them on redeployment.
