from __future__ import annotations

from pathlib import Path

from src.models.skill_models import SkillMetadata


class SkillRegistry:
    """从 skills 目录读取技能元数据。"""

    def __init__(self, skill_root: Path):
        self.skill_root = skill_root
        self._skills: dict[str, SkillMetadata] = {}
        self.discover()

    def discover(self) -> None:
        """扫描所有技能目录。"""

        self._skills.clear()
        if not self.skill_root.exists():
            return
        for skill_dir in self.skill_root.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            metadata = _parse_skill_metadata(skill_file)
            if metadata:
                self._skills[metadata.name] = metadata

    def get(self, skill_name: str) -> SkillMetadata:
        """按名字获取技能。"""

        return self._skills[skill_name]


def _parse_skill_metadata(skill_file: Path) -> SkillMetadata | None:
    """从 SKILL.md 头部提取 name 和 description。"""

    lines = skill_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    name = ""
    description = ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip().strip('"')
        if line.startswith("description:"):
            description = line.split(":", 1)[1].strip().strip('"')
    if not name or not description:
        return None
    return SkillMetadata(name=name, description=description, skill_path=str(skill_file.parent))

