from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import request_safety
from app.request_safety import CORRELATION_HEADER, safe_request_boundary


def test_unexpected_errors_have_safe_support_reference(monkeypatch):
    test_app = FastAPI()
    test_app.middleware("http")(safe_request_boundary)
    logged = {}

    def capture_log(template, *values):
        logged["template"] = template
        logged["values"] = values

    monkeypatch.setattr(request_safety.logger, "error", capture_log)

    @test_app.get("/api/failure")
    async def failure():
        raise RuntimeError("sensitive provider response")

    response = TestClient(test_app, raise_server_exceptions=False).get("/api/failure")

    assert response.status_code == 500
    correlation_id = response.headers[CORRELATION_HEADER]
    assert response.json() == {"detail": {
        "message": "Unexpected server error. Use the reference when requesting support.",
        "correlation_id": correlation_id,
    }}
    assert response.headers["Cache-Control"] == "no-store"
    log_record = repr(logged)
    assert correlation_id in log_record
    assert "RuntimeError" in log_record
    assert "sensitive provider response" not in log_record


def test_successful_requests_are_also_correlated():
    test_app = FastAPI()
    test_app.middleware("http")(safe_request_boundary)

    @test_app.get("/health")
    async def health():
        return {"status": "ok"}

    response = TestClient(test_app).get("/health")
    assert response.status_code == 200
    assert response.headers[CORRELATION_HEADER]
    assert "Cache-Control" not in response.headers
