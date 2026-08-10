from __future__ import annotations

import re
from dataclasses import dataclass

from .config import get_settings
from .security import detect_prompt_injection


@dataclass
class GuardrailCheck:
    passed: bool
    warnings: list[str]
    sanitized_query: str


def validate_news_input(text: str) -> GuardrailCheck:
    if not text or not text.strip():
        message = get_settings().section("conversation")["missing_news_message"]
        return GuardrailCheck(False, [message], "")
    warnings = detect_prompt_injection(text)
    return GuardrailCheck(True, warnings, "")


def validate_user_query(query: str) -> GuardrailCheck:
    cfg = get_settings().section("security")
    cleaned = (query or "").strip()
    if not cleaned:
        cleaned = "Analyze all configured companies based on this news."
    max_chars = int(cfg["max_user_query_characters"])
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]
    warnings = detect_prompt_injection(cleaned)

    advice_markers = cfg["investment_advice_markers"]
    if any(re.search(p, cleaned, flags=re.IGNORECASE) for p in advice_markers):
        warnings.append(
            "Investment-advice wording detected; response is limited to a research-oriented impact suggestion."
        )
    return GuardrailCheck(True, warnings, cleaned)


def validate_output(summary: str, rows: list[dict]) -> dict:
    settings = get_settings()
    cfg = settings.section("security")
    output_cfg = settings.section("output")
    analysis_cfg = settings.section("analysis")
    violations: list[str] = []

    combined = (
        summary
        + " "
        + " ".join(str(r.get("Reason Behind Impact", "")) for r in rows)
        + " "
        + " ".join(str(r.get("Investment Suggestion", "")) for r in rows)
    ).lower()
    for phrase in cfg["prohibited_output_claims"]:
        if phrase.lower() in combined:
            violations.append(f"Prohibited certainty/advice phrase detected: {phrase}")

    allowed_impacts = set(output_cfg["impact_labels"].values())
    allowed_suggestions = set(output_cfg["investment_suggestions"].values())
    min_words = int(analysis_cfg["reason_min_words"])
    max_words = int(analysis_cfg["reason_max_words"])

    for row in rows:
        company = row.get("Company Name", "unknown company")
        if row.get("Impact Direction") not in allowed_impacts:
            violations.append(f"Invalid impact label for {company}")
        if row.get("Investment Suggestion") not in allowed_suggestions:
            violations.append(f"Invalid investment suggestion for {company}")
        reason_words = len(str(row.get("Reason Behind Impact", "")).split())
        if not min_words <= reason_words <= max_words:
            violations.append(
                f"Reason length for {company} must be between {min_words} and {max_words} words"
            )

    return {"passed": not violations, "violations": violations}
