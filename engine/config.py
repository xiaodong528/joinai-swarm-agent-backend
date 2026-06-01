from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    e2b_api_key: str | None = Field(default_factory=lambda: os.getenv("E2B_API_KEY"))
    deepseek_api_key: str | None = Field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY"))
    opencode_model: str = Field(default_factory=lambda: os.getenv("OPENCODE_MODEL", "deepseek/deepseek-v4-pro"))
    e2b_template: str = Field(default_factory=lambda: os.getenv("E2B_OPENCODE_TEMPLATE", "opencode"))
    e2b_timeout_seconds: int = Field(default_factory=lambda: int(os.getenv("E2B_TIMEOUT_SECONDS", "1800")))
    opencode_port: int = Field(default_factory=lambda: int(os.getenv("OPENCODE_PORT", "4096")))
    default_timeout_ms: int = Field(default_factory=lambda: int(os.getenv("ENGINE_DEFAULT_TIMEOUT_MS", "600000")))
    template_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv(
                "ENGINE_TEMPLATE_DIR",
                str(ROOT / "juzhigonfang-team-manager-v0.1" / "juzhigonfang-team-manager"),
            )
        )
    )
    plugins_dir: Path = Field(default_factory=lambda: Path(os.getenv("ENGINE_PLUGINS_DIR", str(ROOT / "plugins" / "plugins"))))

    def validate_runtime(self) -> None:
        missing = []
        if not self.e2b_api_key:
            missing.append("E2B_API_KEY")
        if not self.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY")
        if missing:
            raise RuntimeError(f"Missing required environment variable(s): {', '.join(missing)}")
