import asyncio
from pathlib import Path

import pytest
from fakes import FakeOpenSky, result, scripted

from airspace_common.settings import CollectorSettings
from collector.spool import Spool
from collector.states import OpenSkyUnreachable, collect_slot, run_states

SNAPSHOT = {"time": 1793716290, "states": [["4b1805", "SWR283  "]]}


def run_slot(fake: FakeOpenSky, spool_dir: Path) -> list[float]:
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    asyncio.run(collect_slot(fake, Spool(spool_dir), "pc-daniel", sleep=sleep))
    return sleeps


def test_success_is_spooled_as_states_global(tmp_path: Path, read_pending) -> None:
    fake = FakeOpenSky(scripted(result(200, SNAPSHOT)))
    assert run_slot(fake, tmp_path) == []
    [env] = read_pending(tmp_path)
    assert env["query"] == {"kind": "states_global", "extended": True}
    assert env["collector_id"] == "pc-daniel"
    assert (env["http_status"], env["response"]) == (200, SNAPSHOT)
    assert fake.calls == [("/states/all", {"extended": 1})]


def test_5xx_is_retried_once_after_10_seconds(tmp_path: Path, read_pending) -> None:
    fake = FakeOpenSky(scripted(result(503), result(200, SNAPSHOT)))
    assert run_slot(fake, tmp_path) == [10]
    [env] = read_pending(tmp_path)
    assert env["http_status"] == 200


def test_second_failure_spools_one_failed_envelope(tmp_path: Path, read_pending) -> None:
    fake = FakeOpenSky(scripted(result(0), result(503)))
    run_slot(fake, tmp_path)
    [env] = read_pending(tmp_path)
    assert (env["http_status"], env["response"]) == (503, None)


def test_429_is_spooled_without_retry(tmp_path: Path, read_pending) -> None:
    fake = FakeOpenSky(scripted(result(429, retry_after=600)))
    assert run_slot(fake, tmp_path) == []
    [env] = read_pending(tmp_path)
    assert (env["http_status"], env["retry_after_s"]) == (429, 600)


def _settings(tmp_path: Path) -> CollectorSettings:
    return CollectorSettings(
        collector_id="pi-daniel",
        opensky_client_id="id",
        opensky_client_secret="secret",
        cadence_seconds=1,
        spool_dir=tmp_path,
    )


def test_exits_after_consecutive_unreachable_slots(tmp_path: Path, monkeypatch) -> None:
    # A restart is what refreshes a stale resolv.conf (Pi outage 2026-11-13), so the loop
    # gives up and lets Docker restart the container.
    monkeypatch.setattr("collector.states.RETRY_DELAY_S", 0)
    fake = FakeOpenSky(lambda path, params: result(0))
    with pytest.raises(OpenSkyUnreachable):
        asyncio.run(run_states(_settings(tmp_path), fake, Spool(tmp_path), max_unreachable_slots=3))
    assert len(fake.calls) == 6  # 3 slots, each retried once


def test_a_success_resets_the_unreachable_count(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("collector.states.RETRY_DELAY_S", 0)
    statuses = iter([0, 0, 0, 0, 200, 0, 0, 0, 0, 0, 0])
    fake = FakeOpenSky(lambda path, params: result(next(statuses), SNAPSHOT))
    with pytest.raises(OpenSkyUnreachable):
        asyncio.run(run_states(_settings(tmp_path), fake, Spool(tmp_path), max_unreachable_slots=3))
    # slots: fail, fail, ok, fail, fail, fail -> stops only after the second run of three
    assert len(fake.calls) == 11
