# Data Folder

The application is currently configured to load these two files together:

- `company_exposure_2026_part1.xlsx`
- `company_exposure_2026_part2.xlsx`

They contain different rows, so the combined in-memory table contains the full 2026 demo dataset without duplicate scoring.

Other files are included for reference/backward compatibility:

- `real_company_exposure_2026.csv` — complete dataset in one CSV file.
- `real_company_exposure_2026_reference.xlsx` — complete dataset in one reference workbook.
- `sample_company_exposure.csv` — original fictional XYZ demonstration data.
- `sample_news.txt` — original small sample news file.
- `news/` — five 2026 real-world-style demo news briefs.

Do not list the complete CSV and both part workbooks in `settings.yaml` at the same time unless you intentionally want overlapping inputs. Duplicate exposure rows are removed by default, but keeping one logical source set is clearer.
