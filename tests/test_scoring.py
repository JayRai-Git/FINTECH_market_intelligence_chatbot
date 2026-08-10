from src.market_intel.exposure import ExposureEngine
from src.market_intel.response_builder import build_response
from src.market_intel.schemas import EventDriver, ExtractedEvent


def lithium_event() -> ExtractedEvent:
    return ExtractedEvent(
        topic="Lithium price rebound",
        summary=(
            "Lithium prices are rising as supply tightens and battery-storage demand expands, "
            "creating different operating effects for lithium producers and battery consumers."
        ),
        event_type="commodity_price_increase",
        key_market_points=[
            "Lithium prices are increasing.",
            "Battery storage demand remains strong.",
            "Battery-material consumers may face higher input costs.",
        ],
        drivers=[
            EventDriver(
                entity="Lithium prices",
                direction="increase",
                impact_magnitude=0.9,
                confidence=0.9,
                evidence="The supplied news describes a material rebound in lithium pricing.",
            )
        ],
        risks=["New supply could return if higher prices persist."],
    )


def test_lithium_price_increase_hurts_consumer_and_helps_producer():
    engine = ExposureEngine()
    signals = {x.company: x for x in engine.score(lithium_event())}
    assert signals["Albemarle Corporation"].signal == "UP"
    assert signals["Tesla, Inc."].signal == "DOWN"
    assert signals["Visa Inc."].signal == "NEUTRAL"


def test_specific_company_filter_and_response_shape():
    engine = ExposureEngine()
    selected = engine.resolve_company_query("Please analyze Tesla, Inc. only")
    assert selected == ["Tesla, Inc."]

    signals = engine.score(lithium_event(), selected)
    summary, key_points, impact_counts, rows = build_response(lithium_event(), signals)

    assert summary
    assert key_points
    assert impact_counts["DECREASE"] == 1
    assert len(rows) == 1
    assert rows[0]["Company Name"] == "Tesla, Inc."
    assert rows[0]["Impact Direction"] == "DECREASE"
    assert rows[0]["Investment Suggestion"] == "CAUTION / NEGATIVE WATCH"
    assert 200 <= len(rows[0]["Reason Behind Impact"].split()) <= 220


def test_followup_reuses_previous_company():
    engine = ExposureEngine()
    selected = engine.resolve_company_query("Why?", ["Tesla, Inc."])
    assert selected == ["Tesla, Inc."]


def test_direct_table_question_and_followup():
    engine = ExposureEngine()
    answer, selected = engine.answer_table_question(
        "What products of Tesla, Inc. are present in our list?"
    )
    assert selected == ["Tesla, Inc."]
    assert "Electric vehicles" in answer
    assert "Megapack and stationary battery storage" in answer

    ticker, selected_followup = engine.answer_table_question(
        "What is its ticker?", previous_selected=selected
    )
    assert ticker == "TSLA"
    assert selected_followup == ["Tesla, Inc."]


def test_global_unique_company_names_ignores_previous_company():
    engine = ExposureEngine()
    answer, selected = engine.answer_table_question(
        "Give me unique company names present in our list.",
        previous_selected=["Tesla, Inc."],
    )
    assert selected == []
    assert "Tesla, Inc." in answer
    assert "NVIDIA Corporation" in answer
    assert "Delta Air Lines, Inc." in answer
