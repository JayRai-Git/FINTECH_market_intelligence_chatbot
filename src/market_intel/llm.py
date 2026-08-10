from __future__ import annotations

import json
import re
from typing import Any

from openai import BadRequestError, OpenAI

from .config import get_settings
from .logging_utils import to_json_safe
from .schemas import EvaluationMatrix, ExtractedEvent


def _extract_json(text: str) -> dict:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Model did not return a JSON object.")
    return json.loads(cleaned[start : end + 1])


class MarketLLM:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.cfg = self.settings.section("llm")
        self._openrouter_client: OpenAI | None = None

    def _client(self) -> OpenAI:
        # Reuse one HTTP client for the Streamlit session instead of rebuilding
        # connection state for every extraction/judge call.
        if self._openrouter_client is not None:
            return self._openrouter_client
        if not self.settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is missing.")
        self._openrouter_client = OpenAI(
            api_key=self.settings.openrouter_api_key,
            base_url=self.cfg["openrouter_base_url"],
            timeout=float(self.cfg["timeout_seconds"]),
            default_headers={
                "HTTP-Referer": self.cfg["app_url_header"],
                "X-Title": self.cfg["app_title_header"],
            },
        )
        return self._openrouter_client

    def _chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> dict:
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": float(self.cfg["temperature"]),
            "max_tokens": int(max_tokens),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        use_json = bool(self.cfg["use_json_response_format"])
        if use_json:
            kwargs["response_format"] = {"type": "json_object"}
        client = self._client()
        try:
            response = client.chat.completions.create(**kwargs)
        except BadRequestError:
            # Retry without response_format only for a provider/model 400-level request
            # rejection. The previous code retried on timeouts/network errors too, which
            # could double the wait time before falling back to another model.
            if not use_json:
                raise
            kwargs.pop("response_format", None)
            response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or "{}"
        return _extract_json(content)

    def _openrouter_event_call(self, news_text: str, model: str) -> ExtractedEvent:
        data = self._chat_json(
            model=model,
            system_prompt=self.settings.prompts["system_event_extractor"],
            user_prompt=self.settings.prompts["user_event_extractor"].format(news_text=news_text),
            max_tokens=int(self.cfg["max_tokens"]),
        )
        return ExtractedEvent.model_validate(data)

    def _local_hf_call(self, news_text: str) -> ExtractedEvent:
        from transformers import pipeline

        model = self.cfg["local_hf_model"]
        generator = pipeline(
            "text2text-generation", model=model, token=self.settings.hf_token or None
        )
        prompt = self.settings.prompts["local_hf_event_prompt"].format(news_text=news_text)
        result = generator(
            prompt,
            max_new_tokens=int(self.cfg["local_hf_max_new_tokens"]),
            do_sample=False,
        )[0]["generated_text"]
        return ExtractedEvent.model_validate(_extract_json(result))

    def extract_event(self, news_text: str) -> ExtractedEvent:
        errors: list[str] = []
        for model in [self.cfg["primary_model"], self.cfg["fallback_model"]]:
            try:
                return self._openrouter_event_call(news_text, model)
            except Exception as exc:
                errors.append(f"{model}: {exc}")
        if bool(self.cfg["local_hf_fallback_enabled"]):
            try:
                return self._local_hf_call(news_text)
            except Exception as exc:
                errors.append(f"local_hf: {exc}")
        raise RuntimeError("All configured LLM providers failed. " + " | ".join(errors))

    def judge_response(
        self,
        *,
        news_text: str,
        user_query: str,
        response_summary: str,
        response_rows: list[dict],
    ) -> dict:
        last_error = None
        for model in [self.cfg["primary_model"], self.cfg["fallback_model"]]:
            try:
                prompt = self.settings.prompts["user_judge"].format(
                    user_query=user_query,
                    news_text=news_text,
                    response_summary=response_summary,
                    response_rows=json.dumps(to_json_safe(response_rows), ensure_ascii=False),
                )
                return self._chat_json(
                    model=model,
                    system_prompt=self.settings.prompts["system_judge"],
                    user_prompt=prompt,
                    max_tokens=int(self.cfg["judge_max_tokens"]),
                )
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"LLM judge failed: {last_error}")
