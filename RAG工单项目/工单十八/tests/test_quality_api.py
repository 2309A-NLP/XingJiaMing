from __future__ import annotations

import time

from fastapi.testclient import TestClient

from src.api.main import app


def test_sync_api_returns_report_and_html(sample_documents):
    client = TestClient(app)
    response = client.post(
        "/v1/document/quality-inspection",
        json={
            "file_paths": [
                str(sample_documents["md_one"]),
                str(sample_documents["txt"]),
                str(sample_documents["text_pdf"]),
            ],
            "mode": "sync",
            "include_html_content": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["report"]["summary"]["total_documents"] == 3
    assert payload["html_content"]


def test_async_api_persists_task_and_status(sample_documents):
    client = TestClient(app)
    create_response = client.post(
        "/v1/document/quality-inspection",
        json={
            "file_paths": [str(sample_documents["txt"])],
            "mode": "async",
            "include_html_content": False,
        },
    )

    assert create_response.status_code == 202
    payload = create_response.json()
    assert payload["status"] in {"pending", "running"}

    task_id = payload["task_id"]
    final_payload = payload
    for _ in range(30):
        time.sleep(0.1)
        status_response = client.get(f"/v1/document/quality-inspection/{task_id}")
        final_payload = status_response.json()
        if final_payload["status"] == "completed":
            break

    assert final_payload["status"] == "completed"
    assert final_payload["report"]["summary"]["total_documents"] == 1


def test_scan_pdf_returns_readable_ocr_error_and_resume(sample_documents):
    client = TestClient(app)
    create_response = client.post(
        "/v1/document/quality-inspection",
        json={
            "file_paths": [str(sample_documents["scan_pdf"])],
            "mode": "async",
            "include_html_content": False,
        },
    )

    task_id = create_response.json()["task_id"]
    final_payload = None
    for _ in range(30):
        time.sleep(0.1)
        status_response = client.get(f"/v1/document/quality-inspection/{task_id}")
        final_payload = status_response.json()
        if final_payload["status"] == "completed":
            break

    assert final_payload is not None
    assert final_payload["status"] == "completed"
    assert final_payload["report"]["summary"]["routing_decisions"]["scan.pdf"]["parser_type"] == "ocr"
    assert final_payload["report"]["summary"]["routing_decisions"]["scan.pdf"]["execution_mode"] == "route_only"
    assert final_payload["error_message"] is None

    resume_response = client.post(f"/v1/document/quality-inspection/{task_id}/resume")
    assert resume_response.status_code == 202
    assert resume_response.json()["task_id"] == task_id


def test_sync_api_returns_simhash_candidates_for_near_duplicates(sample_documents):
    client = TestClient(app)
    response = client.post(
        "/v1/document/quality-inspection",
        json={
            "file_paths": [
                str(sample_documents["near_dup_one"]),
                str(sample_documents["near_dup_two"]),
            ],
            "mode": "sync",
            "include_html_content": False,
            "config_overrides": {
                "simhash": {"enabled": True, "distance_threshold": 12},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["report"]["duplicate_summary"]["simhash_candidates"]
