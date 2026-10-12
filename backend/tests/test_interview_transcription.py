from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import interviews as interviews_api
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.main import app
from app.services import transcription_service as module


class FakeDb:
    pass


@pytest.fixture
def authenticated_client(monkeypatch):
    user_id = uuid4()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: FakeDb()
    monkeypatch.setattr(interviews_api, "ensure_user", lambda db, owner: None)
    try:
        yield TestClient(app), user_id
    finally:
        app.dependency_overrides.clear()


def webm_audio(payload: bytes = b"voice") -> bytes:
    return b"\x1a\x45\xdf\xa3" + payload


@pytest.mark.parametrize(
    ("audio", "content_type", "extension"),
    [
        (webm_audio(), "audio/webm;codecs=opus", "webm"),
        (b"\x00\x00\x00\x18ftypmp42voice", "audio/mp4", "mp4"),
    ],
)
def test_chrome_webm_and_safari_mp4_are_accepted(audio, content_type, extension):
    result = module.transcription_service.validate(audio, content_type, 2)
    assert result.extension == extension


def test_authenticated_transcription_success_and_response_schema(authenticated_client, monkeypatch):
    client, _ = authenticated_client
    monkeypatch.setattr(
        interviews_api.transcription_service,
        "transcribe",
        lambda **kwargs: {
            "transcript": "A clear interview answer.",
            "duration_seconds": 12.5,
            "provider": "openai",
            "model": "gpt-4o-mini-transcribe",
        },
    )

    response = client.post(
        "/api/v1/interviews/transcribe",
        files={"audio": ("answer.webm", webm_audio(), "audio/webm")},
        data={"duration_seconds": "12.5"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "transcript": "A clear interview answer.",
        "duration_seconds": 12.5,
        "provider": "openai",
        "model": "gpt-4o-mini-transcribe",
    }


def test_unauthenticated_transcription_is_rejected():
    response = TestClient(app).post(
        "/api/v1/interviews/transcribe",
        files={"audio": ("answer.webm", webm_audio(), "audio/webm")},
        data={"duration_seconds": "2"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("audio", "content_type", "code"),
    [
        (b"", "audio/webm", "EMPTY_AUDIO"),
        (b"not audio", "image/png", "UNSUPPORTED_AUDIO_TYPE"),
        (b"not a webm", "audio/webm", "UNSUPPORTED_AUDIO_TYPE"),
    ],
)
def test_audio_validation_rejects_empty_or_unsupported(audio, content_type, code, monkeypatch):
    monkeypatch.setattr(module, "track_event", lambda **kwargs: None)
    with pytest.raises(module.TranscriptionInputError) as caught:
        module.transcription_service.transcribe(
            user_id=uuid4(), audio=audio, content_type=content_type, duration_seconds=2
        )
    assert caught.value.code == code


def test_audio_validation_rejects_oversized_file_and_duration(monkeypatch):
    monkeypatch.setattr(module, "track_event", lambda **kwargs: None)
    monkeypatch.setattr(settings, "interview_audio_max_bytes", 6)
    with pytest.raises(module.TranscriptionInputError) as oversized:
        module.transcription_service.transcribe(
            user_id=uuid4(), audio=webm_audio(b"long"), content_type="audio/webm", duration_seconds=2
        )
    assert oversized.value.code == "AUDIO_TOO_LARGE"

    monkeypatch.setattr(settings, "interview_audio_max_bytes", 100)
    monkeypatch.setattr(settings, "interview_audio_max_seconds", 300)
    with pytest.raises(module.TranscriptionInputError) as too_long:
        module.transcription_service.transcribe(
            user_id=uuid4(), audio=webm_audio(), content_type="audio/webm", duration_seconds=301
        )
    assert too_long.value.code == "INVALID_AUDIO_DURATION"


def test_provider_failure_is_safe_and_empty_transcript_is_rejected(monkeypatch):
    monkeypatch.setattr(module, "track_event", lambda **kwargs: None)
    monkeypatch.setattr(module.ai_client, "transcribe_audio", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("PRIVATE AUDIO")))
    with pytest.raises(module.TranscriptionProviderError) as provider_error:
        module.transcription_service.transcribe(
            user_id=uuid4(), audio=webm_audio(), content_type="audio/webm", duration_seconds=2
        )
    assert provider_error.value.code == "TRANSCRIPTION_UNAVAILABLE"

    monkeypatch.setattr(module.ai_client, "transcribe_audio", lambda **kwargs: ("", None))
    with pytest.raises(module.TranscriptionInputError) as empty:
        module.transcription_service.transcribe(
            user_id=uuid4(), audio=webm_audio(), content_type="audio/webm", duration_seconds=2
        )
    assert empty.value.code == "EMPTY_TRANSCRIPT"


def test_success_metrics_do_not_contain_transcript(monkeypatch):
    events = []
    monkeypatch.setattr(module, "track_event", lambda **kwargs: events.append(kwargs))
    monkeypatch.setattr(module.ai_client, "transcribe_audio", lambda **kwargs: ("PRIVATE TRANSCRIPT", 3.0))

    result = module.transcription_service.transcribe(
        user_id=uuid4(), audio=webm_audio(), content_type="audio/webm", duration_seconds=2
    )

    assert result["transcript"] == "PRIVATE TRANSCRIPT"
    assert events[0]["event_name"] == "interview_transcription_completed"
    assert "PRIVATE TRANSCRIPT" not in repr(events[0])
    assert set(events[0]["metadata"]) == {"audio_size_bytes", "audio_duration_seconds", "model"}
