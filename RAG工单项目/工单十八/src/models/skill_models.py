from __future__ import annotations

from pydantic import BaseModel


class SkillMetadata(BaseModel):
    """技能元数据。"""

    name: str
    description: str
    skill_path: str

