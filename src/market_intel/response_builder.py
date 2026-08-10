from __future__ import annotations

from collections import Counter

from .config import get_settings
from .schemas import CompanySignal, ExtractedEvent


def _truncate_words(text: str, max_words: int) -> str:
    words = str(text).split()
    if len(words) <= max_words:
        return str(text).strip()
    return " ".join(words[:max_words]).rstrip(" ,;:") + "…"


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = " ".join(str(item).split()).strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out


def _impact_label(signal: str) -> str:
    labels = get_settings().section("output")["impact_labels"]
    return labels.get(signal, labels["NEUTRAL"])


def _investment_suggestion(signal: str) -> str:
    suggestions = get_settings().section("output")["investment_suggestions"]
    return suggestions.get(signal, suggestions["NEUTRAL"])


def _reason_why(event: ExtractedEvent, signal: CompanySignal) -> str:
    """Build one company-specific reason inside the configured word range."""
    cfg = get_settings().section("analysis")
    minimum = max(1, int(cfg["reason_min_words"]))
    maximum = max(minimum, int(cfg["reason_max_words"]))

    # The requested range is controlled entirely from settings.yaml. Keeping the
    # default at 200-220 makes the cell concise while still satisfying 200-300.
    impact = _impact_label(signal.signal).lower()
    products = (
        ", ".join(signal.products_affected)
        if signal.products_affected
        else "no directly matched configured product"
    )
    exposures = (
        ", ".join(signal.matched_exposures)
        if signal.matched_exposures
        else "no direct configured raw-material or market-driver exposure"
    )
    evidence = (
        "; ".join(signal.matched_driver_evidence[:2])
        if signal.matched_driver_evidence
        else "the supplied news does not establish a strong direct exposure link"
    )
    risks = (
        "; ".join(event.risks[:2])
        if event.risks
        else "event duration, severity and price transmission remain uncertain"
    )

    if signal.signal == "UP":
        mechanism = (
            "The modeled transmission is favorable because this company is configured as a producer, seller, or beneficiary of the affected input or product. "
            "Tighter supply, firmer prices, stronger demand, or better utilization can support revenue or margins if the company can continue producing and delivering."
        )
    elif signal.signal == "DOWN":
        mechanism = (
            "The modeled transmission is unfavorable because this company consumes or depends on the affected input or product. "
            "Higher procurement cost, lower availability, production delays, or weaker demand can pressure volumes or margins unless inventory, contracts, hedges, substitution, or price pass-through offset the effect."
        )
    else:
        mechanism = (
            "The configured exposure does not provide enough direct evidence for a material positive or negative operating impact. "
            "Second-order effects through customers, suppliers, financing or market sentiment are possible, but the current news does not establish a strong enough direct path for a directional signal."
        )

    reason = " ".join(
        [
            f"{signal.company} ({signal.ticker}) operates in {signal.industry} with the configured region {signal.region or 'not specified'}. For this company only, the model assigns a potential {impact} impact. The impacted product mapping is {products}, and the directly matched exposure is {exposures}.",
            f"The news event is summarized as: {event.summary} The company-specific evidence used in this record is: {evidence}. {mechanism}",
            f"The calculated impact score is {signal.score:.4f} with confidence {signal.confidence:.2f}. This score combines event direction and magnitude with source confidence, company sensitivity, exposure weight and match strength. It is a relative research signal, not a prediction of an exact share-price move.",
            f"Important uncertainty for {signal.company} includes {risks}. Actual financial impact can differ because of supplier contracts, inventory buffers, hedging, geographic diversification, product mix, pricing power and management actions. The market may also have partly priced the event before publication. Therefore this record should be reassessed when new company disclosures, commodity prices, supplier information, demand data or regional developments materially change the exposure."
        ]
    )
    reason = " ".join(reason.split())

    # Pad only when necessary, using company-specific analytical caveats.
    padding = [
        f"The conclusion is specific to {signal.company} and is not copied from another company record.",
        f"For {signal.company}, the strongest monitored variables are the affected product, matched exposure, regional relevance and the persistence of the reported event.",
        "A change in any of those variables can alter the direction, score or confidence in a later run.",
    ]
    for sentence in padding:
        if len(reason.split()) >= minimum:
            break
        reason = f"{reason} {sentence}"

    return _truncate_words(reason, maximum)


def build_response(
    event: ExtractedEvent,
    signals: list[CompanySignal],
) -> tuple[str, list[str], dict[str, int], list[dict]]:
    """Return exactly the four response sections required by the UI."""
    cfg = get_settings().section("analysis")
    summary = _truncate_words(event.summary, int(cfg["summary_max_words"]))
    max_points = int(cfg["max_key_market_points"])

    company_evidence: list[str] = []
    for signal in signals:
        company_evidence.extend(signal.matched_driver_evidence)
    key_points = _dedupe(event.key_market_points + company_evidence)[:max_points]
    if not key_points:
        key_points = ["No additional market point was extracted beyond the attached news summary."]

    counts = Counter(_impact_label(signal.signal) for signal in signals)
    impact_counts = {
        "INCREASE": int(counts.get("INCREASE", 0)),
        "DECREASE": int(counts.get("DECREASE", 0)),
        "NEUTRAL": int(counts.get("NEUTRAL", 0)),
    }

    rows: list[dict] = []
    for signal in signals:
        rows.append(
            {
                "Ticker / Code": signal.ticker,
                "Company Name": signal.company,
                "Impact Direction": _impact_label(signal.signal),
                "Investment Suggestion": _investment_suggestion(signal.signal),
                "Impact Score": round(float(signal.score), 4),
                "Confidence": round(float(signal.confidence), 2),
                "Company Impacted Product": (
                    ", ".join(signal.products_affected)
                    if signal.products_affected
                    else "No directly impacted configured product"
                ),
                "Reason Behind Impact": _reason_why(event, signal),
            }
        )

    return summary, key_points, impact_counts, rows
