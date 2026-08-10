from __future__ import annotations

from typing import Literal, TypedDict
from pydantic import BaseModel, Field

Direction = Literal["increase", "decrease", "positive", "negative", "uncertain"]
Signal = Literal["UP", "DOWN", "NEUTRAL"]
ImpactLabel = Literal["INCREASE", "DECREASE", "NEUTRAL"]


class EventDriver(BaseModel):
    entity: str
    direction: Direction
    impact_magnitude: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""


class ExtractedEvent(BaseModel):
    topic: str
    summary: str
    event_type: str
    key_market_points: list[str] = Field(default_factory=list)
    drivers: list[EventDriver] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class CompanySignal(BaseModel):
    company: str
    trading_name: str = ""
    ticker: str
    industry: str
    region: str = ""
    signal: Signal
    score: float
    confidence: float
    products_affected: list[str] = Field(default_factory=list)
    matched_exposures: list[str] = Field(default_factory=list)
    rationale: str = ""
    matched_driver_evidence: list[str] = Field(default_factory=list)


class EvaluationMatrix(BaseModel):
    grounding: int = Field(ge=0, le=5)
    relevance: int = Field(ge=0, le=5)
    causal_reasoning: int = Field(ge=0, le=5)
    format_compliance: int = Field(ge=0, le=5)
    safety: int = Field(ge=0, le=5)
    uncertainty_calibration: int = Field(ge=0, le=5)
    overall_score: float = Field(ge=0.0, le=100.0)
    passed: bool
    judge_mode: str
    notes: list[str] = Field(default_factory=list)


class AnalysisState(TypedDict, total=False):
    source_text: str
    source_name: str
    source_type: str
    user_query: str
    previous_selected_companies: list[str]
    requested_companies: list[str]
    input_guardrail: dict
    injection_warnings: list[str]
    event: dict
    signals: list[dict]
    response_summary: str
    response_key_points: list[str]
    response_impact_counts: dict[str, int]
    response_rows: list[dict]
    output_guardrail: dict
    evaluation: dict
