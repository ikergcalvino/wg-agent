import pytest
from pydantic import ValidationError

from api.config import Settings, load_settings

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestSettings:
    def test_api_key_is_required(self, monkeypatch):
        monkeypatch.delenv("API_KEY")
        with pytest.raises(ValidationError, match="api_key"):
            Settings()

    @pytest.mark.parametrize("key", ["", "short-key"])
    def test_api_key_must_be_long_enough(self, monkeypatch, key):
        monkeypatch.setenv("API_KEY", key)
        with pytest.raises(ValidationError, match="at least 16 characters"):
            Settings()

    @pytest.mark.parametrize(("value", "expected"), [("debug", "DEBUG"), ("Warning", "WARNING"), ("ERROR", "ERROR")])
    def test_log_level_is_case_insensitive(self, monkeypatch, value, expected):
        monkeypatch.setenv("LOG_LEVEL", value)
        assert Settings().log_level == expected

    def test_invalid_log_level_exits_with_a_readable_message(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "verbose")
        with pytest.raises(SystemExit, match="^Invalid configuration: LOG_LEVEL: Input should be 'DEBUG'"):
            load_settings()

    def test_load_settings_exits_with_a_readable_message(self, monkeypatch):
        monkeypatch.delenv("API_KEY")
        with pytest.raises(SystemExit, match="^Invalid configuration: API_KEY: Field required$"):
            load_settings()

    def test_origin_list_is_comma_separated(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
        assert Settings().cors_origin_list == ["https://a.example", "https://b.example"]
