import pytest

from app.config import LOCAL_ALLOWED_ORIGINS, get_settings


def test_allowed_origins_default_to_local_development(monkeypatch):
    monkeypatch.delenv("ATHENA_ALLOWED_ORIGINS", raising=False)
    assert get_settings().allowed_origins == LOCAL_ALLOWED_ORIGINS


def test_allowed_origins_are_normalized_and_deduplicated(monkeypatch):
    monkeypatch.setenv(
        "ATHENA_ALLOWED_ORIGINS",
        "https://datascienceconsultants.github.io/, https://example.test,https://example.test",
    )
    assert get_settings().allowed_origins == (
        "https://datascienceconsultants.github.io",
        "https://example.test",
    )


def test_allowed_origins_reject_wildcard(monkeypatch):
    monkeypatch.setenv("ATHENA_ALLOWED_ORIGINS", "*")
    with pytest.raises(ValueError, match="explicit origins"):
        get_settings()
