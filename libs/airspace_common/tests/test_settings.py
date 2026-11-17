from pathlib import Path

import pytest

from airspace_common.settings import CollectorSettings

REQUIRED = {
    "COLLECTOR_ID": "pc-daniel",
    "OPENSKY_CLIENT_ID": "client-id",
    "OPENSKY_CLIENT_SECRET": "s3cr3t-value",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    monkeypatch.chdir(tmp_path)  # keep any real .env out of the test
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_defaults_match_the_pipeline_doc(env: pytest.MonkeyPatch) -> None:
    settings = CollectorSettings()
    assert settings.cadence_seconds == 90
    assert settings.upload_enabled is True
    assert settings.flight_lists_enabled is True
    assert settings.spool_dir == Path("spool")


def test_a_leftover_offset_in_dotenv_is_ignored(env: pytest.MonkeyPatch) -> None:
    # Collectors set up before M1.21 still have OFFSET_SECONDS in their .env.
    env.setenv("OFFSET_SECONDS", "45")
    assert not hasattr(CollectorSettings(), "offset_seconds")


def test_secret_never_appears_in_repr(env: pytest.MonkeyPatch) -> None:
    assert "s3cr3t-value" not in repr(CollectorSettings())


def test_values_are_read_from_dotenv_in_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key in REQUIRED:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(f"{k}={v}" for k, v in REQUIRED.items()) + "\nOFFSET_SECONDS=45\n"
    )
    settings = CollectorSettings()
    assert settings.collector_id == "pc-daniel"
