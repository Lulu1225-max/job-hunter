from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from time import perf_counter
from uuid import UUID

from app.core.config import settings
from app.services.ai.client import ai_client
from app.services.analytics import elapsed_ms, track_event


@dataclass(frozen=True)
class AudioFormat:
    extension: str
    content_type: str


class TranscriptionInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TranscriptionProviderError(RuntimeError):
    def __init__(self, code: str = "TRANSCRIPTION_UNAVAILABLE") -> None:
        super().__init__("Transcription provider failed")
        self.code = code


MIME_FORMATS = {
    "audio/webm": AudioFormat("webm", "audio/webm"),
    "video/webm": AudioFormat("webm", "audio/webm"),
    "audio/mp4": AudioFormat("mp4", "audio/mp4"),
    "video/mp4": AudioFormat("mp4", "audio/mp4"),
    "audio/m4a": AudioFormat("m4a", "audio/m4a"),
    "audio/x-m4a": AudioFormat("m4a", "audio/m4a"),
    "audio/wav": AudioFormat("wav", "audio/wav"),
    "audio/x-wav": AudioFormat("wav", "audio/wav"),
    "audio/ogg": AudioFormat("ogg", "audio/ogg"),
    "audio/mpeg": AudioFormat("mp3", "audio/mpeg"),
}


def _signature_matches(audio: bytes, extension: str) -> bool:
    if extension == "webm":
        return audio.startswith(b"\x1a\x45\xdf\xa3")
    if extension in {"mp4", "m4a"}:
        return len(audio) >= 12 and audio[4:8] == b"ftyp"
    if extension == "wav":
        return len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"
    if extension == "ogg":
        return audio.startswith(b"OggS")
    if extension == "mp3":
        return audio.startswith(b"ID3") or (len(audio) >= 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0)
    return False


class TranscriptionService:
    def validate(self, audio: bytes, claimed_content_type: str | None, duration_seconds: float) -> AudioFormat:
        if not audio:
            raise TranscriptionInputError("EMPTY_AUDIO", "The recording is empty")
        if len(audio) > settings.interview_audio_max_bytes:
            raise TranscriptionInputError("AUDIO_TOO_LARGE", "The recording is too large")
        if not isfinite(duration_seconds) or duration_seconds <= 0 or duration_seconds > settings.interview_audio_max_seconds:
            raise TranscriptionInputError("INVALID_AUDIO_DURATION", "The recording duration is invalid")
        content_type = (claimed_content_type or "").split(";", 1)[0].strip().casefold()
        audio_format = MIME_FORMATS.get(content_type)
        if not audio_format or not _signature_matches(audio, audio_format.extension):
            raise TranscriptionInputError("UNSUPPORTED_AUDIO_TYPE", "The recording format is not supported")
        return audio_format

    def transcribe(
        self,
        *,
        user_id: UUID,
        audio: bytes,
        content_type: str | None,
        duration_seconds: float,
    ) -> dict:
        started = perf_counter()
        try:
            audio_format = self.validate(audio, content_type, duration_seconds)
            transcript, provider_duration = ai_client.transcribe_audio(
                audio=audio,
                filename=f"interview-answer.{audio_format.extension}",
                content_type=audio_format.content_type,
            )
            if not transcript:
                raise TranscriptionInputError("EMPTY_TRANSCRIPT", "No speech could be transcribed")
            safe_duration = provider_duration if provider_duration is not None else duration_seconds
            track_event(
                user_id=user_id,
                event_name="interview_transcription_completed",
                status="success",
                latency_ms=elapsed_ms(started),
                metadata={
                    "audio_size_bytes": len(audio),
                    "audio_duration_seconds": round(safe_duration, 2),
                    "model": settings.openai_transcription_model,
                },
            )
            return {
                "transcript": transcript,
                "duration_seconds": safe_duration,
                "provider": "openai",
                "model": settings.openai_transcription_model,
            }
        except TranscriptionInputError as exc:
            track_event(
                user_id=user_id,
                event_name="interview_transcription_failed",
                status="failure",
                error_type=exc.code,
                latency_ms=elapsed_ms(started),
                metadata={"audio_size_bytes": len(audio), "audio_duration_seconds": round(duration_seconds, 2)},
            )
            raise
        except Exception as exc:
            error_type = "TRANSCRIPTION_TIMEOUT" if "timeout" in type(exc).__name__.casefold() else "TRANSCRIPTION_UNAVAILABLE"
            track_event(
                user_id=user_id,
                event_name="interview_transcription_failed",
                status="failure",
                error_type=error_type,
                latency_ms=elapsed_ms(started),
                metadata={"audio_size_bytes": len(audio), "audio_duration_seconds": round(duration_seconds, 2)},
            )
            raise TranscriptionProviderError(error_type) from exc


transcription_service = TranscriptionService()
