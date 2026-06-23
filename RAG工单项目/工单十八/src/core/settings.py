from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv(override=True)


class Settings(BaseModel):
    """项目配置。"""

    app_host: str
    app_port: int
    app_env: str
    log_level: str
    data_dir: Path
    log_dir: Path
    storage_dir: Path
    task_state_dir: Path
    report_output_dir: Path
    skill_root_dir: Path
    assessment_config_path: Path
    async_file_count_threshold: int
    async_total_size_threshold_mb: int
    max_file_count: int
    max_path_length: int
    max_field_length: int
    ocr_provider: str
    ocr_execution_enabled: bool | None
    ocr_fail_on_error: bool | None
    ocr_command: str
    paddleocr_executable: str
    paddleocr_lang: str
    mineru_executable: str
    mineru_output_dir: Path
    ocr_render_scale: float
    ocr_timeout_seconds: int
    ocr_vision_char_threshold: int
    vision_color_std_threshold: float
    multimodal_api_key: str
    multimodal_base_url: str
    multimodal_model: str

    def ensure_directories(self) -> None:
        """把运行期目录提前建好。"""

        for path in [
            self.data_dir,
            self.log_dir,
            self.storage_dir,
            self.task_state_dir,
            self.report_output_dir,
            self.mineru_output_dir,
            self.skill_root_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def load_assessment_config(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """读取 YAML 配置并应用请求级覆盖。"""

        with self.assessment_config_path.open("r", encoding="utf-8") as file:
            base_config = yaml.safe_load(file) or {}
        base_config.setdefault("ocr", {})
        if self.ocr_execution_enabled is not None:
            base_config["ocr"]["execution_enabled"] = self.ocr_execution_enabled
        if self.ocr_fail_on_error is not None:
            base_config["ocr"]["fail_on_error"] = self.ocr_fail_on_error
        if not overrides:
            return base_config
        return _deep_merge(base_config, overrides)


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_bool_env(name: str) -> bool | None:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return None

    normalized_value = raw_value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} 只能配置为 true/false、1/0、yes/no 或 on/off")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """加载一次配置并缓存。"""

    settings = Settings(
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=int(os.getenv("APP_PORT", "8018")),
        app_env=os.getenv("APP_ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        data_dir=Path(os.getenv("DATA_DIR", "./data")),
        log_dir=Path(os.getenv("LOG_DIR", "./logs")),
        storage_dir=Path(os.getenv("STORAGE_DIR", "./storage")),
        task_state_dir=Path(os.getenv("TASK_STATE_DIR", "./storage/tasks")),
        report_output_dir=Path(os.getenv("REPORT_OUTPUT_DIR", "./storage/reports")),
        skill_root_dir=Path(os.getenv("SKILL_ROOT_DIR", "./skills")),
        assessment_config_path=Path(os.getenv("ASSESSMENT_CONFIG_PATH", "./config/assessment_config.yaml")),
        async_file_count_threshold=int(os.getenv("ASYNC_FILE_COUNT_THRESHOLD", "10")),
        async_total_size_threshold_mb=int(os.getenv("ASYNC_TOTAL_SIZE_THRESHOLD_MB", "10")),
        max_file_count=int(os.getenv("MAX_FILE_COUNT", "2000")),
        max_path_length=int(os.getenv("MAX_PATH_LENGTH", "260")),
        max_field_length=int(os.getenv("MAX_FIELD_LENGTH", "2000")),
        ocr_provider=os.getenv("OCR_PROVIDER", "auto"),
        ocr_execution_enabled=_read_bool_env("OCR_EXECUTION_ENABLED"),
        ocr_fail_on_error=_read_bool_env("OCR_FAIL_ON_ERROR"),
        ocr_command=os.getenv("OCR_COMMAND", ""),
        paddleocr_executable=os.getenv("PADDLEOCR_EXECUTABLE", ""),
        paddleocr_lang=os.getenv("PADDLEOCR_LANG", "ch"),
        mineru_executable=os.getenv("MINERU_EXECUTABLE", ""),
        mineru_output_dir=Path(os.getenv("MINERU_OUTPUT_DIR", "./storage/ocr")),
        ocr_render_scale=float(os.getenv("OCR_RENDER_SCALE", "2.0")),
        ocr_timeout_seconds=int(os.getenv("OCR_TIMEOUT_SECONDS", "600")),
        ocr_vision_char_threshold=int(os.getenv("OCR_VISION_CHAR_THRESHOLD", "200")),
        vision_color_std_threshold=float(os.getenv("VISION_COLOR_STD_THRESHOLD", "30")),
        multimodal_api_key=os.getenv("MULTIMODAL_API_KEY", ""),
        multimodal_base_url=os.getenv("MULTIMODAL_BASE_URL", ""),
        multimodal_model=os.getenv("MULTIMODAL_MODEL", "mimo-v2.5"),
    )
    settings.ensure_directories()
    return settings
