"""Archive upload to R2 and local retention (docs/04-pipelines.md#p1--collector, "Archive").

Runs right after the daily compaction: `rclone copy` puts `spool/archive/` into
`<RCLONE_REMOTE>/<collector_id>/` (finished files only), then local archives older than
`ARCHIVE_RETENTION_DAYS` are deleted, but only those R2 holds at the same size. If uploads stop
working, nothing local is deleted.

The rclone remote is configured from the environment (`RCLONE_CONFIG_<REMOTE>_*`), built from
`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`. The Pi's R2 token can only read
and write `airspace-archive`.
"""

import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from pathlib import Path

import structlog

log = structlog.get_logger()

Runner = Callable[[list[str], dict[str, str]], str]
DAY_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})\.parquet$")


def rclone_env(remote: str, account_id: str, access_key_id: str, secret: str) -> dict[str, str]:
    prefix = f"RCLONE_CONFIG_{remote.upper()}_"
    return {
        prefix + "TYPE": "s3",
        prefix + "PROVIDER": "Cloudflare",
        prefix + "ENDPOINT": f"https://{account_id}.r2.cloudflarestorage.com",
        prefix + "ACCESS_KEY_ID": access_key_id,
        prefix + "SECRET_ACCESS_KEY": secret,
    }


def expired_local_archives(
    local: Mapping[str, int], remote: Mapping[str, int], today: date, retention_days: int
) -> list[str]:
    """Local archives (relative path -> size) to delete: dated more than `retention_days` before
    `today`, and present in R2 with the same size."""
    cutoff = today - timedelta(days=retention_days)
    doomed = []
    for rel, size in sorted(local.items()):
        m = DAY_NAME.search(rel)
        if m and date.fromisoformat(m.group(1)) < cutoff and remote.get(rel) == size:
            doomed.append(rel)
    return doomed


def _subprocess_runner(args: list[str], env: dict[str, str]) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True, env=env)
    return result.stdout


class ArchiveUploader:
    def __init__(
        self,
        spool_root: Path,
        target: str,
        env: Mapping[str, str],
        retention_days: int,
        run: Runner = _subprocess_runner,
    ) -> None:
        self.archive = spool_root / "archive"
        self.target = target
        self.env = {**os.environ, **env}
        self.retention_days = retention_days
        self._run = run

    def run(self, today: date) -> list[str]:
        """Uploads, then deletes expired local archives. Returns the deleted relative paths."""
        common = ["--s3-no-check-bucket", "--exclude", "*.tmp"]
        self._run(
            ["rclone", "copy", str(self.archive), self.target, *common, "--retries", "10"],
            self.env,
        )
        listing = self._run(["rclone", "lsjson", "-R", "--files-only", self.target], self.env)
        remote = {f["Path"]: int(f["Size"]) for f in json.loads(listing or "[]")}
        local = {
            p.relative_to(self.archive).as_posix(): p.stat().st_size
            for p in self.archive.rglob("*.parquet")
        }
        doomed = expired_local_archives(local, remote, today, self.retention_days)
        for rel in doomed:
            (self.archive / rel).unlink()
        log.info("archive_uploaded", local_files=len(local), remote_files=len(remote),
                 deleted=doomed)  # fmt: skip
        return doomed
