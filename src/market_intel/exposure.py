from __future__ import annotations

import re
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from .config import get_settings
from .schemas import CompanySignal, ExtractedEvent


def _direction_multiplier(direction: str) -> float:
    return {
        "increase": 1.0,
        "positive": 1.0,
        "decrease": -1.0,
        "negative": -1.0,
        "uncertain": 0.0,
    }.get(direction, 0.0)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


class ExposureEngine:
    REQUIRED_COLUMNS = [
        "company",
        "trading_name",
        "ticker",
        "industry",
        "region",
        "product",
        "exposure_type",
        "material_or_driver",
        "usage_reason",
        "sensitivity",
        "exposure_weight",
    ]

    NUMERIC_COLUMNS = ["sensitivity", "exposure_weight"]

    def __init__(self) -> None:
        self.settings = get_settings()
        self.cfg = self.settings.section("analysis")
        self.embed_cfg = self.settings.section("embeddings")
        self.data_cfg = self.settings.raw.get("exposure_data", {})
        self.source_files = self.settings.paths("company_exposure_csv")
        self.df = self._load_exposure_data()
        self._model = None
        self._exposure_vectors = None

    def _read_exposure_file(self, path) -> pd.DataFrame:
        """Read one configured CSV/XLSX exposure file into a DataFrame."""
        if not path.exists():
            raise FileNotFoundError(f"Company exposure file was not found: {path}")

        suffix = path.suffix.lower()
        if suffix == ".csv":
            frame = pd.read_csv(path)
        elif suffix in {".xlsx", ".xlsm"}:
            configured_sheet = self.data_cfg.get("excel_sheet_name", "Company Exposure")
            excel = pd.ExcelFile(path, engine="openpyxl")
            if configured_sheet in excel.sheet_names:
                sheet_name = configured_sheet
            else:
                sheet_name = excel.sheet_names[0]
            frame = pd.read_excel(excel, sheet_name=sheet_name)
        else:
            raise ValueError(
                f"Unsupported company exposure file type: {path.name}. "
                "Use CSV, XLSX, or XLSM."
            )

        # Normalize accidental whitespace in headers. Extra columns are allowed.
        frame.columns = [str(column).strip() for column in frame.columns]
        missing = [column for column in self.REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(
                f"Exposure file {path.name} is missing required columns: "
                + ", ".join(missing)
            )

        # Fail early when numeric model parameters are blank or malformed.
        for column in self.NUMERIC_COLUMNS:
            numeric = pd.to_numeric(frame[column], errors="coerce")
            invalid = numeric.isna()
            if invalid.any():
                bad_rows = [str(int(i) + 2) for i in frame.index[invalid][:10]]
                raise ValueError(
                    f"Exposure file {path.name} has invalid {column} values "
                    f"at spreadsheet row(s): {', '.join(bad_rows)}"
                )
            frame[column] = numeric.astype(float)

        # Keep the origin of each row for debugging without changing scoring logic.
        frame["_source_file"] = path.name
        return frame

    def _load_exposure_data(self) -> pd.DataFrame:
        """Load and combine every file listed under paths.company_exposure_csv."""
        frames = [self._read_exposure_file(path) for path in self.source_files]
        combined = pd.concat(frames, ignore_index=True, sort=False)

        # Avoid double-scoring the same exposure when overlapping files are listed.
        if bool(self.data_cfg.get("deduplicate_rows", True)):
            dedupe_columns = [
                "company",
                "trading_name",
                "ticker",
                "industry",
                "region",
                "product",
                "exposure_type",
                "material_or_driver",
                "usage_reason",
                "sensitivity",
                "exposure_weight",
            ]
            combined = combined.drop_duplicates(subset=dedupe_columns, keep="first")

        combined = combined.reset_index(drop=True).fillna("")
        if combined.empty:
            raise ValueError("Configured company exposure files contain no usable rows.")
        return combined

    @property
    def source_file_names(self) -> list[str]:
        return [path.name for path in self.source_files]

    @property
    def companies(self) -> list[str]:
        return list(dict.fromkeys(self.df["company"].astype(str).tolist()))

    def company_catalog(self) -> list[dict]:
        cols = ["company", "trading_name", "ticker", "industry", "region"]
        return self.df[cols].drop_duplicates(subset=["company"]).to_dict("records")

    def answer_table_question(
        self,
        user_query: str,
        previous_selected: list[str] | None = None,
    ) -> tuple[str | None, list[str]]:
        """Answer company-master/table questions directly from the combined exposure data.

        Rules:
        - If a company is explicitly named, answer only the requested field(s)
          for that company.
        - If no company is named but the query clearly asks about the complete
          list/table (for example "unique company names present in our list"),
          answer from all rows.
        - If the query is a follow-up such as "what are its products?", reuse
          the previously selected company.
        - Otherwise return None so the normal news-impact workflow can run.
        """
        lookup_cfg = self.settings.section("table_lookup")
        if not bool(lookup_cfg.get("enabled", True)):
            return None, []

        query = _normalize(user_query)
        if not query:
            return None, []

        requested_fields: list[tuple[str, str]] = []
        for field_name, field_cfg in lookup_cfg["fields"].items():
            keywords = [_normalize(x) for x in field_cfg.get("keywords", [])]
            if any(keyword and keyword in query for keyword in keywords):
                requested_fields.append((field_name, str(field_cfg["output_column"])))

        # No configured table field was requested: let the market-impact flow continue.
        if not requested_fields:
            return None, []

        # First resolve only companies explicitly present in THIS question.
        # Passing an empty previous selection prevents short global queries from
        # accidentally inheriting the company from the previous chat turn.
        explicit_selected = self.resolve_company_query(
            user_query,
            previous_selected=[],
        )

        global_markers = [
            _normalize(x) for x in lookup_cfg.get("global_scope_markers", [])
        ]
        asks_complete_table = any(
            marker and marker in query for marker in global_markers
        )

        if explicit_selected:
            selected = explicit_selected
            rows = self.df[self.df["company"].isin(selected)]
        elif asks_complete_table:
            # Global table question: deliberately ignore previous company context.
            selected = []
            rows = self.df
        else:
            # Normal follow-up table question, e.g. "what are its products?".
            selected = self.resolve_company_query(
                user_query,
                previous_selected=previous_selected or [],
            )
            if not selected:
                return None, []
            rows = self.df[self.df["company"].isin(selected)]

        if rows.empty:
            return None, []

        def unique_values(column: str) -> list[str]:
            values: list[str] = []
            seen: set[str] = set()
            for value in rows[column].astype(str).tolist():
                clean = " ".join(value.split()).strip()
                key = clean.lower()
                if clean and key not in seen:
                    seen.add(key)
                    values.append(clean)
            return values

        # One requested field => values only, with no summary/report/explanation.
        if len(requested_fields) == 1:
            _, column = requested_fields[0]
            return ", ".join(unique_values(column)), selected

        # Multiple requested table fields => concise labelled values only.
        parts: list[str] = []
        for field_name, column in requested_fields:
            label = field_name.replace("_", " ").title()
            parts.append(f"{label}: {', '.join(unique_values(column))}")
        return " | ".join(parts), selected

    def resolve_company_query(
        self,
        user_query: str,
        previous_selected: list[str] | None = None,
    ) -> list[str]:
        """Return explicit company matches; empty list means analyze all companies."""
        query = _normalize(user_query)
        previous_selected = previous_selected or []
        if not query:
            return previous_selected or []

        conv_cfg = self.settings.section("conversation")
        all_markers = conv_cfg["all_company_markers"]
        if any(marker in query for marker in all_markers):
            return []

        catalog = self.company_catalog()
        # First prefer unambiguous direct substring/ticker matches. This prevents common
        # generic legal/entity tokens from making unrelated companies look similar.
        direct_matches: list[str] = []
        query_tokens = set(query.split())
        for row in catalog:
            company = str(row["company"])
            company_alias = _normalize(company)
            trading_alias = _normalize(row.get("trading_name", ""))
            ticker_alias = _normalize(row.get("ticker", ""))
            if (
                (company_alias and company_alias in query)
                or (trading_alias and trading_alias in query)
                or (ticker_alias and ticker_alias in query_tokens)
            ):
                if company not in direct_matches:
                    direct_matches.append(company)
        if direct_matches:
            return direct_matches

        matches: list[str] = []
        threshold = float(self.cfg["company_name_fuzzy_threshold"])
        generic = set(conv_cfg["generic_company_tokens"])
        query_distinctive = [t for t in query.split() if t not in generic]
        for row in catalog:
            company = str(row["company"])
            aliases = [
                _normalize(company),
                _normalize(row.get("trading_name", "")),
                _normalize(row.get("ticker", "")),
            ]
            explicit = False
            for alias in [a for a in aliases if a]:
                alias_distinctive = [t for t in alias.split() if t not in generic]
                if not alias_distinctive or not query_distinctive:
                    continue
                # Fuzzy token overlap tolerates small typing/plural errors such as
                # "Tesla Inx" vs "Tesla, Inc.".
                token_threshold = float(
                    self.settings.section("table_lookup").get("fuzzy_token_threshold", 0.82)
                )
                matched_alias_tokens = 0
                for alias_token in set(alias_distinctive):
                    if any(
                        alias_token == query_token
                        or SequenceMatcher(None, alias_token, query_token).ratio() >= token_threshold
                        for query_token in set(query_distinctive)
                    ):
                        matched_alias_tokens += 1
                if (
                    matched_alias_tokens >= 1
                    and matched_alias_tokens / max(1, len(set(alias_distinctive))) >= 0.60
                ):
                    explicit = True
                    break
                q_compact = " ".join(query_distinctive)
                a_compact = " ".join(alias_distinctive)
                if len(q_compact) >= 5 and len(a_compact) >= 5 and SequenceMatcher(None, q_compact, a_compact).ratio() >= threshold:
                    explicit = True
                    break
            if explicit and company not in matches:
                matches.append(company)

        if matches:
            return matches

        followup_markers = set(conv_cfg["followup_markers"])
        if bool(self.cfg["reuse_previous_company_filter_for_followups"]) and previous_selected:
            if any(marker in query for marker in followup_markers) or len(query.split()) <= 8:
                return previous_selected
        return []

    def _ensure_embeddings(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            self.embed_cfg["model_name"],
            token=self.settings.hf_token or None,
        )
        texts = (
            self.df["material_or_driver"].astype(str)
            + " | "
            + self.df["product"].astype(str)
            + " | "
            + self.df["usage_reason"].astype(str)
        ).tolist()
        self._exposure_vectors = self._model.encode(
            texts,
            normalize_embeddings=bool(self.embed_cfg["normalize_embeddings"]),
        )

    def _semantic_matches(self, entity: str) -> list[tuple[int, float]]:
        entity_l = _normalize(entity)
        exact: list[tuple[int, float]] = []
        for i, row in self.df.iterrows():
            material = _normalize(row["material_or_driver"])
            product = _normalize(row["product"])
            if (
                entity_l == material
                or (material and material in entity_l)
                or (entity_l and entity_l in material)
                or (product and product in entity_l)
                or (entity_l and entity_l in product)
            ):
                exact.append((i, 1.0))
        if exact:
            return exact[: int(self.embed_cfg["top_k_exposures"])]

        self._ensure_embeddings()
        q = self._model.encode(
            [entity], normalize_embeddings=bool(self.embed_cfg["normalize_embeddings"])
        )[0]
        sims = np.dot(self._exposure_vectors, q)
        order = np.argsort(-sims)[: int(self.embed_cfg["top_k_exposures"])]
        threshold = float(self.embed_cfg["semantic_match_threshold"])
        return [(int(i), float(sims[i])) for i in order if float(sims[i]) >= threshold]

    def score(
        self,
        event: ExtractedEvent,
        company_filter: list[str] | None = None,
    ) -> list[CompanySignal]:
        selected = set(company_filter or self.companies)
        contributions: dict[str, list[dict]] = {company: [] for company in selected}

        for driver in event.drivers:
            for idx, similarity in self._semantic_matches(driver.entity):
                row = self.df.iloc[idx]
                company = str(row["company"])
                if company not in selected:
                    continue
                raw = (
                    _direction_multiplier(driver.direction)
                    * float(row["sensitivity"])
                    * float(row["exposure_weight"])
                    * float(driver.impact_magnitude)
                    * float(driver.confidence)
                    * float(similarity)
                )
                contributions.setdefault(company, []).append(
                    {
                        "score": raw,
                        "entity": driver.entity,
                        "material": str(row["material_or_driver"]),
                        "product": str(row["product"]),
                        "reason": str(row["usage_reason"]),
                        "confidence": float(driver.confidence) * float(similarity),
                        "evidence": driver.evidence,
                    }
                )

        results: list[CompanySignal] = []
        up = float(self.cfg["direction_up_threshold"])
        down = float(self.cfg["direction_down_threshold"])
        lo, hi = float(self.cfg["score_clip_min"]), float(self.cfg["score_clip_max"])
        c_floor, c_ceil = float(self.cfg["confidence_floor"]), float(self.cfg["confidence_ceiling"])

        for company in self.companies:
            if company not in selected:
                continue
            company_rows = self.df[self.df["company"] == company]
            meta = company_rows.iloc[0]
            items = contributions.get(company, [])
            if items:
                score = float(np.clip(sum(x["score"] for x in items), lo, hi))
                signal = "UP" if score >= up else "DOWN" if score <= down else "NEUTRAL"
                confidence = float(
                    np.clip(np.mean([x["confidence"] for x in items]), c_floor, c_ceil)
                )
                products = sorted({x["product"] for x in items})
                matched = sorted({f'{x["material"]} → {x["product"]}' for x in items})
                evidence = [x["evidence"] for x in items if x.get("evidence")]
                top = sorted(items, key=lambda x: abs(x["score"]), reverse=True)[:3]
                rationale = "; ".join(
                    f'{x["entity"]} affects {x["product"]} because {x["reason"]}' for x in top
                )
            else:
                score = 0.0
                signal = "NEUTRAL"
                confidence = c_floor
                products = []
                matched = []
                evidence = []
                rationale = "No material event-to-configured-exposure match was found."

            results.append(
                CompanySignal(
                    company=company,
                    trading_name=str(meta.get("trading_name", "")),
                    ticker=str(meta["ticker"]),
                    industry=str(meta["industry"]),
                    region=str(meta.get("region", "")),
                    signal=signal,
                    score=round(score, 4),
                    confidence=round(confidence, 4),
                    products_affected=products,
                    matched_exposures=matched,
                    rationale=rationale,
                    matched_driver_evidence=list(dict.fromkeys(evidence)),
                )
            )
        return sorted(results, key=lambda x: abs(x.score), reverse=True)
