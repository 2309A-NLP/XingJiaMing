from __future__ import annotations

from pathlib import Path

from src.core.settings import Settings


def test_ensure_directories_creates_runtime_structure(tmp_path: Path):
    settings = Settings(
        app_host="127.0.0.1",
        app_port=8018,
        app_env="test",
        log_level="INFO",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        storage_dir=tmp_path / "storage",
        task_state_dir=tmp_path / "storage" / "tasks",
        report_output_dir=tmp_path / "storage" / "reports",
        skill_root_dir=tmp_path / "skills",
        assessment_config_path=tmp_path / "config" / "assessment_config.yaml",
        async_file_count_threshold=10,
        async_total_size_threshold_mb=10,
        max_file_count=10,
        max_path_length=260,
        max_field_length=2000,
        ocr_provider="auto",
        ocr_execution_enabled=False,
        ocr_fail_on_error=False,
        ocr_command="",
        paddleocr_executable="",
        paddleocr_lang="ch",
        mineru_executable="",
        mineru_output_dir=tmp_path / "storage" / "ocr",
        ocr_render_scale=2.0,
        ocr_timeout_seconds=60,
        ocr_vision_char_threshold=200,
        vision_color_std_threshold=30.0,
        multimodal_api_key="",
        multimodal_base_url="",
        multimodal_model="mimo-v2.5",
    )

    settings.ensure_directories()

    assert settings.data_dir.exists()
    assert settings.log_dir.exists()
    assert settings.storage_dir.exists()
    assert settings.task_state_dir.exists()
    assert settings.report_output_dir.exists()
    assert settings.mineru_output_dir.exists()
    assert settings.skill_root_dir.exists()
