"""Resolve edition paths without changing the existing interior installation."""

from dataclasses import dataclass
import json
import os
from pathlib import Path


@dataclass(frozen=True)
class EditionContext:
    id: str
    root: Path

    @property
    def content_dir(self):
        return self.root if self.id == "interior" else self.root / "content" / self.id

    @property
    def runtime_dir(self):
        return self.root / "ニュース収集" if self.id == "interior" else self.root / "runtime" / self.id

    @property
    def config_dir(self):
        return self.root / "ニュース収集" if self.id == "interior" else self.root / "editions" / self.id

    @property
    def collection_settings_path(self):
        return self.config_dir / ("department_settings.json" if self.id == "interior" else "settings.json")

    @property
    def collection_prompt_path(self):
        return self.config_dir / ("プロンプト.md" if self.id == "interior" else "prompts/collection.md")

    @property
    def insights_prompt_path(self):
        return self.root / ".agent/prompts/insights_generation_prompt.md" if self.id == "interior" else self.config_dir / "prompts/insights.md"

    @property
    def idea_angles_path(self):
        return self.config_dir / "idea_angles.json"

    @property
    def products_path(self):
        return self.config_dir / "tg_products.json"

    @property
    def config(self):
        data = json.loads(self.collection_settings_path.read_text(encoding="utf-8-sig"))
        config = data.get(self.id)
        if not isinstance(config, dict):
            raise ValueError(f"Edition configuration missing: {self.id}: {self.collection_settings_path}")
        return config

    @property
    def subject_name(self):
        return self.config.get("subject_name", "内装" if self.id == "interior" else "外装")

    @property
    def image_generation(self):
        return self.config.get("image_generation", {"enabled": self.id == "interior", "provider": "gemini" if self.id == "interior" else "none"})

    def ensure_directories(self):
        # Read first: invalid/missing config must fail before creating or writing outputs.
        self.config
        for directory in (self.content_dir, self.runtime_dir, self.content_dir / "images", self.content_dir / "page_images"):
            directory.mkdir(parents=True, exist_ok=True)


def get_edition(edition_id=None, root=None):
    edition_id = (edition_id if edition_id is not None else os.environ.get("DAILYNEWS_EDITION", "interior")).strip().lower()
    if edition_id not in {"interior", "exterior"}:
        raise ValueError(f"Unknown DailyNews edition: {edition_id!r}; expected interior or exterior")
    return EditionContext(edition_id, Path(root).resolve() if root else Path(__file__).resolve().parents[1])
