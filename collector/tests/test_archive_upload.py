import json
from datetime import date
from pathlib import Path

import pytest

from collector.archive_upload import (
    ArchiveUploader,
    expired_local_archives,
    rclone_env,
)

TODAY = date(2026, 12, 20)


def test_only_archives_past_retention_and_safely_in_r2_are_deleted() -> None:
    local = {
        "states/2026-11-19.parquet": 100,  # 31 days old, in R2 with the same size -> delete
        "states/2026-11-20.parquet": 100,  # exactly 30 days old -> keep
        "states/2026-11-18.parquet": 100,  # old, but R2 holds a different size -> keep
        "flights/2026-11-17.parquet": 5,  # old, missing from R2 -> keep
        "flights/2026-11-19.parquet": 5,  # old, in R2 -> delete
    }
    remote = {
        "states/2026-11-19.parquet": 100,
        "states/2026-11-20.parquet": 100,
        "states/2026-11-18.parquet": 99,
        "flights/2026-11-19.parquet": 5,
    }
    assert expired_local_archives(local, remote, TODAY, retention_days=30) == [
        "flights/2026-11-19.parquet",
        "states/2026-11-19.parquet",
    ]


def test_files_without_a_date_name_are_never_deleted() -> None:
    assert expired_local_archives({"states/notes.parquet": 1}, {"states/notes.parquet": 1},
                                  TODAY, 30) == []  # fmt: skip


def test_rclone_gets_the_cloudflare_remote_from_the_environment() -> None:
    env = rclone_env("r2", "acct123", "key-id", "secret")
    assert env["RCLONE_CONFIG_R2_TYPE"] == "s3"
    assert env["RCLONE_CONFIG_R2_PROVIDER"] == "Cloudflare"
    assert env["RCLONE_CONFIG_R2_ENDPOINT"] == "https://acct123.r2.cloudflarestorage.com"
    assert env["RCLONE_CONFIG_R2_ACCESS_KEY_ID"] == "key-id"
    assert env["RCLONE_CONFIG_R2_SECRET_ACCESS_KEY"] == "secret"


class FakeRclone:
    def __init__(self, remote_listing: str) -> None:
        self.calls: list[list[str]] = []
        self.listing = remote_listing

    def __call__(self, args: list[str], env: dict[str, str]) -> str:
        self.calls.append(args)
        return self.listing if args[1] == "lsjson" else ""


def _archive(tmp_path: Path) -> Path:
    for rel in ("states/2026-11-01.parquet", "states/2026-12-19.parquet"):
        (tmp_path / "archive" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "archive" / rel).write_bytes(b"x" * 10)
    (tmp_path / "archive/states/2026-12-19.parquet.tmp").write_bytes(b"partial")
    return tmp_path


def test_upload_copies_finished_archives_then_prunes(tmp_path: Path) -> None:
    root = _archive(tmp_path)
    listing = json.dumps(
        [
            {"Path": "states/2026-11-01.parquet", "Size": 10},
            {"Path": "states/2026-12-19.parquet", "Size": 10},
        ]
    )
    rclone = FakeRclone(listing)
    uploader = ArchiveUploader(root, "r2:airspace-archive/pi-daniel", {}, 30, run=rclone)
    deleted = uploader.run(TODAY)
    copy = rclone.calls[0]
    assert copy[:4] == ["rclone", "copy", str(root / "archive"), "r2:airspace-archive/pi-daniel"]
    assert "--exclude" in copy and "*.tmp" in copy and "--s3-no-check-bucket" in copy
    assert deleted == ["states/2026-11-01.parquet"]
    assert not (root / "archive/states/2026-11-01.parquet").exists()
    assert (root / "archive/states/2026-12-19.parquet").exists()


def test_nothing_is_deleted_when_the_upload_fails(tmp_path: Path) -> None:
    root = _archive(tmp_path)

    def failing(args: list[str], env: dict[str, str]) -> str:
        raise RuntimeError("network down")

    uploader = ArchiveUploader(root, "r2:airspace-archive/pi-daniel", {}, 30, run=failing)
    with pytest.raises(RuntimeError):
        uploader.run(TODAY)
    assert (root / "archive/states/2026-11-01.parquet").exists()
