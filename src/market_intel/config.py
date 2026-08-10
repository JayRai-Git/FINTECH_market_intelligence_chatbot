from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import os

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseModel):
    """Application settings loaded from YAML plus runtime environment secrets."""

    raw: dict
    prompts: dict
    project_root: Path = PROJECT_ROOT

    def section(self, name: str) -> dict:
        return self.raw[name]

    def paths(self, key: str) -> list[Path]:
        """Return one or many configured project-relative paths.

        `paths.company_exposure_csv` is intentionally backward compatible:
        it may be either a single string or a YAML list of CSV/XLSX filenames.
        Other path settings can continue to be simple strings.
        """
        value = self.raw["paths"][key]
        if isinstance(value, (str, Path)):
            values = [value]
        elif isinstance(value, list):
            values = value
        else:
            raise TypeError(
                f"paths.{key} must be a filename string or a list of filename strings."
            )

        resolved: list[Path] = []
        for item in values:
            text = str(item).strip()
            if not text:
                continue
            path = Path(text)
            resolved.append(path if path.is_absolute() else self.project_root / path)

        if not resolved:
            raise ValueError(f"paths.{key} does not contain any usable filenames.")
        return resolved

    def path(self, key: str) -> Path:
        """Return a single configured path.

        Use `paths()` for settings that intentionally contain multiple files.
        """
        resolved = self.paths(key)
        if len(resolved) != 1:
            raise ValueError(
                f"paths.{key} contains {len(resolved)} files; use settings.paths('{key}') instead."
            )
        return resolved[0]

    def _credential_env_name(self, config_key: str, default_name: str) -> str:
        cfg = self.raw.get("credentials", {})
        return str(cfg.get(config_key, default_name)).strip() or default_name

    @property
    def openrouter_api_key(self) -> str:
        env_name = self._credential_env_name("openrouter_env_var", "OPENROUTER_API_KEY")
        return os.getenv(env_name, "").strip()

    @property
    def hf_token(self) -> str:
        env_name = self._credential_env_name("hf_env_var", "HF_TOKEN")
        return os.getenv(env_name, "").strip()

    def tokens_ready(self) -> bool:
        cfg = self.raw.get("credentials", {})
        require_both = bool(cfg.get("require_both_for_analysis", True))
        if require_both:
            return bool(self.openrouter_api_key and self.hf_token)
        return bool(self.openrouter_api_key)

    def set_runtime_tokens(
        self,
        *,
        openrouter_api_key: str = "",
        hf_token: str = "",
    ) -> None:
        """Set credentials for the current Python/Streamlit process only.

        This intentionally does not modify the project's .env file. Existing
        non-empty environment values are preserved when a blank value is passed.
        """
        openrouter_env = self._credential_env_name(
            "openrouter_env_var", "OPENROUTER_API_KEY"
        )
        hf_env = self._credential_env_name("hf_env_var", "HF_TOKEN")

        openrouter_value = str(openrouter_api_key or "").strip()
        hf_value = str(hf_token or "").strip()

        if openrouter_value:
            os.environ[openrouter_env] = openrouter_value
        if hf_value:
            os.environ[hf_env] = hf_value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    prompts_path = PROJECT_ROOT / "config" / "prompts.yaml"
    with settings_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    with prompts_path.open("r", encoding="utf-8") as f:
        prompts = yaml.safe_load(f)
    return Settings(raw=raw, prompts=prompts)
