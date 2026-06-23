from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.core.settings import get_settings


class QualityInspectionRequest(BaseModel):
    """质检请求。"""

    folder_path: str | None = Field(default=None, max_length=2000)
    file_paths: list[str] | None = None
    mode: Literal["sync", "async", "auto"] = "auto"
    include_html_content: bool = True
    resume_existing: bool = True
    config_overrides: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_request(self) -> "QualityInspectionRequest":
        """统一做参数校验。"""

        settings = get_settings()
        if not self.folder_path and not self.file_paths:
            raise ValueError("folder_path 和 file_paths 至少提供一个")

        if self.file_paths:
            if len(self.file_paths) > settings.max_file_count:
                raise ValueError(f"file_paths 数量不能超过 {settings.max_file_count}")
            for file_path in self.file_paths:
                _validate_local_path(file_path, settings.max_path_length)

        if self.folder_path:
            _validate_local_path(self.folder_path, settings.max_path_length)

        if self.config_overrides:
            for key in self.config_overrides.keys():
                if len(key) > settings.max_field_length:
                    raise ValueError("config_overrides 的键过长")
        return self


def _validate_local_path(path_value: str, max_length: int) -> None:
    """只允许本机路径，挡掉 URL 和超长输入。"""

    if not path_value.strip():
        raise ValueError("路径不能为空")
    if len(path_value) > max_length:
        raise ValueError(f"路径长度不能超过 {max_length}")
    lowered = path_value.lower()
    if lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("file://"):
        raise ValueError("仅支持本机路径，不支持 URL")

