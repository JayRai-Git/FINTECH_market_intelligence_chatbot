from __future__ import annotations

from .config import get_settings
from .llm import MarketLLM
from .schemas import EvaluationMatrix


class ResponseEvaluator:
    def __init__(self, llm: MarketLLM | None = None) -> None:
        self.settings = get_settings()
        self.cfg = self.settings.section("judge")
        self.analysis_cfg = self.settings.section("analysis")
        self.llm = llm or MarketLLM()

    def _normalize(self, payload: dict, mode: str) -> EvaluationMatrix:
        dimensions = list(self.cfg["dimensions"])
        max_score = int(self.cfg["max_dimension_score"])
        scores = {}
        for name in dimensions:
            try:
                score = int(round(float(payload.get(name, 0))))
            except Exception:
                score = 0
            scores[name] = max(0, min(max_score, score))

        total = sum(scores.values())
        overall = round(100.0 * total / (len(dimensions) * max_score), 1)
        notes = payload.get("notes", [])
        if isinstance(notes, str):
            notes = [notes]

        return EvaluationMatrix(
            **scores,
            overall_score=overall,
            passed=overall >= float(self.cfg["passing_score"]),
            judge_mode=mode,
            notes=[str(x) for x in notes][:5],
        )

    def _deterministic_score(
        self,
        *,
        user_query: str,
        summary: str,
        rows: list[dict],
        output_guardrail: dict,
        mode: str,
        note: str,
    ) -> EvaluationMatrix:
        """Fast local quality score. No network/LLM call is made here."""
        min_words = int(self.analysis_cfg["reason_min_words"])
        max_words = int(self.analysis_cfg["reason_max_words"])
        output_cfg = self.settings.section("output")
        required_columns = set(output_cfg["table_columns"])

        format_ok = bool(rows) and all(set(r.keys()) == required_columns for r in rows)
        lengths_ok = all(
            min_words <= len(str(r["Reason Behind Impact"]).split()) <= max_words
            for r in rows
        )
        allowed_impacts = set(output_cfg["impact_labels"].values())
        impacts_ok = all(r["Impact Direction"] in allowed_impacts for r in rows)
        allowed_suggestions = set(output_cfg["investment_suggestions"].values())
        suggestions_ok = all(r["Investment Suggestion"] in allowed_suggestions for r in rows)
        grounded = bool(summary.strip()) and all(
            str(r["Reason Behind Impact"]).strip() for r in rows
        )
        relevant = bool(user_query.strip()) and bool(rows)
        causal = all(
            len(str(r["Reason Behind Impact"]).split()) >= min_words for r in rows
        )
        uncertainty = all(
            any(
                token in str(r["Reason Behind Impact"]).lower()
                for token in [
                    "uncertain",
                    "not a forecast",
                    "screening signal",
                    "can differ",
                    "not as guaranteed",
                ]
            )
            for r in rows
        )

        payload = {
            "grounding": 5 if grounded else 2,
            "relevance": 5 if relevant else 2,
            "causal_reasoning": 5 if causal else 2,
            "format_compliance": 5
            if format_ok and lengths_ok and impacts_ok and suggestions_ok
            else 2,
            "safety": 5 if output_guardrail.get("passed", False) else 1,
            "uncertainty_calibration": 5 if uncertainty else 3,
            "notes": [note],
        }
        return self._normalize(payload, mode)

    def _apply_guardrail_to_llm_result(
        self, result: EvaluationMatrix, output_guardrail: dict
    ) -> EvaluationMatrix:
        if output_guardrail.get("passed", False):
            return result

        result.safety = min(result.safety, 1)
        result.overall_score = round(
            100.0
            * sum(
                [
                    result.grounding,
                    result.relevance,
                    result.causal_reasoning,
                    result.format_compliance,
                    result.safety,
                    result.uncertainty_calibration,
                ]
            )
            / 30.0,
            1,
        )
        result.passed = result.overall_score >= float(self.cfg["passing_score"])
        return result

    def evaluate(
        self,
        *,
        news_text: str,
        user_query: str,
        response_summary: str,
        response_rows: list[dict],
        output_guardrail: dict,
    ) -> EvaluationMatrix:
        # Always compute the fast score first. This is local and normally takes
        # milliseconds, so the sidebar can still show an evaluation for every response.
        fast_result = self._deterministic_score(
            user_query=user_query,
            summary=response_summary,
            rows=response_rows,
            output_guardrail=output_guardrail,
            mode="deterministic_fast",
            note="Fast local evaluation passed; remote LLM judge was not required.",
        )

        if not bool(self.cfg.get("enabled", True)):
            return fast_result

        strategy = str(self.cfg.get("strategy", "always_llm")).strip().lower()
        escalation_threshold = float(
            self.cfg.get("llm_escalation_score_below", self.cfg["passing_score"])
        )

        # Fast production path: only escalate questionable responses to the remote LLM.
        if strategy == "deterministic_first":
            if (
                output_guardrail.get("passed", False)
                and fast_result.overall_score >= escalation_threshold
            ):
                return fast_result

        # "always_llm" preserves the old behavior. In deterministic_first mode this
        # block is reached only when the fast checks indicate the response needs review.
        try:
            payload = self.llm.judge_response(
                news_text=news_text,
                user_query=user_query,
                response_summary=response_summary,
                response_rows=response_rows,
            )
            result = self._normalize(payload, "llm_judge")
            return self._apply_guardrail_to_llm_result(result, output_guardrail)
        except Exception:
            return self._deterministic_score(
                user_query=user_query,
                summary=response_summary,
                rows=response_rows,
                output_guardrail=output_guardrail,
                mode="deterministic_fallback",
                note="Remote LLM judge was unavailable; local evaluation was used.",
            )
