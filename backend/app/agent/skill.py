from dataclasses import dataclass
from pathlib import Path
from app.config import SKILLS_DIR


@dataclass
class Skill:
    name: str
    description: str
    path: Path

    def read_skill_md(self) -> str:
        return (self.path / "SKILL.md").read_text()


def _parse_description(skill_md: str) -> str:
    """Extract description from YAML frontmatter, else first non-blank line."""
    lines = skill_md.splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if line.startswith("description:"):
                return line[len("description:"):].strip().strip('"\'')
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped != "---":
            return stripped[:200]
    return ""


def load_skills() -> list[Skill]:
    skills = []
    if not SKILLS_DIR.exists():
        return skills
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_md_path = skill_dir / "SKILL.md"
        if skill_dir.is_dir() and skill_md_path.exists():
            content = skill_md_path.read_text(errors="replace")
            desc = _parse_description(content)
            skills.append(Skill(name=skill_dir.name, description=desc, path=skill_dir))
    return skills
