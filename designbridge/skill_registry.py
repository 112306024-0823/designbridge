# designbridge/skill_registry.py
"""Skill Registry: reads SKILL.md files and exposes them to the Router LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Skills that participate in routing decisions
ROUTING_SKILL_IDS = ["layout-planner", "style-advisor", "design-adjuster"]

SKILL_ID_TO_ROUTING_KEY: dict[str, str] = {
    "layout-planner":  "layout",
    "style-advisor":   "style",
    "design-adjuster": "design_adjuster",
}


@dataclass
class SkillCard:
    skill_id: str       # directory name: "layout-planner"
    name: str           # YAML frontmatter: name
    description: str    # YAML frontmatter: description
    when_to_use: str    # extracted from "## When to Use" section
    routing_key: str    # corresponding RoutingDecision value


class SkillRegistry:
    """Loads and caches SkillCard objects parsed from SKILL.md files."""

    def __init__(self, skills_root: Optional[Path] = None) -> None:
        if skills_root is None:
            # Same logic as config.py: _root = Path(__file__).resolve().parent.parent
            _root = Path(__file__).resolve().parent.parent
            skills_root = _root / "skills"
        self._skills_root = skills_root
        self._cache: Optional[dict[str, SkillCard]] = None

    def _parse_skill_md(self, skill_id: str) -> Optional[SkillCard]:
        """Parse a single SKILL.md and return a SkillCard, or None on failure."""
        skill_md_path = self._skills_root / skill_id / "SKILL.md"
        if not skill_md_path.is_file():
            return None

        text = skill_md_path.read_text(encoding="utf-8")

        # --- Extract YAML frontmatter (between first pair of ---) ---
        name = ""
        description = ""
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if fm_match:
            frontmatter = fm_match.group(1)
            name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
            desc_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
            if name_match:
                name = name_match.group(1).strip()
            if desc_match:
                description = desc_match.group(1).strip()

        # --- Extract "## When to Use" section (up to next ##) ---
        when_to_use = ""
        wtu_match = re.search(
            r"##\s+When to Use\s*\n(.*?)(?=\n##|\Z)",
            text,
            re.DOTALL,
        )
        if wtu_match:
            when_to_use = wtu_match.group(1).strip()

        routing_key = SKILL_ID_TO_ROUTING_KEY.get(skill_id, skill_id)

        return SkillCard(
            skill_id=skill_id,
            name=name or skill_id,
            description=description,
            when_to_use=when_to_use,
            routing_key=routing_key,
        )

    def load(self) -> dict[str, SkillCard]:
        """Load (and cache) all routing skills. Returns dict keyed by skill_id."""
        if self._cache is not None:
            return self._cache

        result: dict[str, SkillCard] = {}
        for skill_id in ROUTING_SKILL_IDS:
            card = self._parse_skill_md(skill_id)
            if card is not None:
                result[skill_id] = card
            else:
                print(f"[SkillRegistry] Warning: could not load skill '{skill_id}'")
        self._cache = result
        return result

    def get_routing_skills(self) -> list[SkillCard]:
        """Return list of SkillCards for routing skills."""
        return list(self.load().values())

    def format_for_prompt(self) -> str:
        """Format all routing skills into a text block for the Router LLM prompt."""
        cards = self.get_routing_skills()
        if not cards:
            return "(no skills available)"

        parts: list[str] = []
        for card in cards:
            block = (
                f"### {card.name} (routing_key: {card.routing_key})\n"
                f"**Description:** {card.description}\n"
                f"**When to Use:**\n{card.when_to_use}"
            )
            parts.append(block)
        return "\n\n".join(parts)


# Module-level singleton
_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    """Return the module-level SkillRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
