import logging
import sys
from unittest.mock import Mock

from app.core.runtime_logging import get_server_logger
from app.services.ai import client


def test_runtime_logger_is_error_level_and_has_stream_handler():
    logger=get_server_logger()
    assert logger.name=="uvicorn.error"
    assert logger.isEnabledFor(logging.ERROR)
    assert any(isinstance(handler,logging.StreamHandler) for handler in logger.handlers)
    assert any(getattr(handler,"stream",None) in {sys.stderr,sys.__stderr__} for handler in logger.handlers)


def test_openai_failure_calls_runtime_logger_without_exception_payload(monkeypatch):
    error=RuntimeError("sk-secret FULL PROMPT PRIVATE RESUME PRIVATE JD PRIVATE ANSWER")
    called=Mock();monkeypatch.setattr(client.logger,"error",called)
    client._log_openai_failure(error,"interview_answer_generation","experience")
    called.assert_called_once()
    rendered=" ".join(str(value) for value in called.call_args.args)
    assert "openai_call_failed" in rendered
    for private in ("sk-secret","FULL PROMPT","PRIVATE RESUME","PRIVATE JD","PRIVATE ANSWER"):
        assert private not in rendered
