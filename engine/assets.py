from __future__ import annotations

from pathlib import Path

from engine.config import Settings
from engine.hooks import merge_plugin_config, proxy_hooks_plugin


EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", "dist"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


class AssetManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def validate(self) -> None:
        if not self.settings.template_dir.exists():
            raise FileNotFoundError(f"Template directory not found: {self.settings.template_dir}")
        if not (self.settings.template_dir / "opencode.json").exists():
            raise FileNotFoundError(f"Template opencode.json not found: {self.settings.template_dir / 'opencode.json'}")
        for name in ("session-export.ts", "session-import.ts"):
            if not (self.settings.plugins_dir / name).exists():
                raise FileNotFoundError(f"Plugin not found: {self.settings.plugins_dir / name}")

    def iter_template_files(self) -> list[tuple[Path, str]]:
        root = self.settings.template_dir
        files: list[tuple[Path, str]] = []
        for item in root.rglob("*"):
            rel = item.relative_to(root)
            if any(part in EXCLUDED_DIRS for part in rel.parts):
                continue
            if item.is_file() and item.suffix not in EXCLUDED_SUFFIXES:
                files.append((item, rel.as_posix()))
        return files

    def read_template_file(self, src: Path, rel: str) -> str:
        text = src.read_text(encoding="utf-8")
        if rel == "opencode.json":
            return merge_plugin_config(text, self.settings.opencode_model)
        return text

    def plugin_files(self) -> dict[str, str]:
        return {
            "session-export.ts": (self.settings.plugins_dir / "session-export.ts").read_text(encoding="utf-8"),
            "session-import.ts": (self.settings.plugins_dir / "session-import.ts").read_text(encoding="utf-8"),
            "proxy-hooks.ts": proxy_hooks_plugin(),
        }
