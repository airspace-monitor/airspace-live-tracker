"""One `ops.job_runs` row per run (docs/04-pipelines.md#p4--orchestrated-jobs)."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime

import psycopg

from airspace_common.settings import JobsSettings


@dataclass
class Run:
    conn: psycopg.Connection
    rows_out: int | None = field(default=None)


@contextmanager
def recorded_run(
    settings: JobsSettings, job: str, window_start: datetime, window_end: datetime
) -> Iterator[Run]:
    """Connects as `jobs`, marks the run `running`, and yields a connection whose work commits
    in one transaction. The row ends `ok` with `rows_out`, or `failed` with the error."""
    password = settings.jobs_password.get_secret_value()
    with psycopg.connect(
        host=settings.jobs_db_host,
        user="jobs",
        dbname="airspace",
        password=password,
        autocommit=True,
    ) as log_conn:
        run_id = log_conn.execute(
            "INSERT INTO ops.job_runs (job, window_start, window_end, started_at, status)"
            " VALUES (%s, %s, %s, now(), 'running') RETURNING run_id",
            (job, window_start, window_end),
        ).fetchone()[0]  # type: ignore[index]
        try:
            with psycopg.connect(
                host=settings.jobs_db_host, user="jobs", dbname="airspace", password=password
            ) as work_conn:
                run = Run(work_conn)
                yield run
        except Exception as exc:
            log_conn.execute(
                "UPDATE ops.job_runs SET status = 'failed', finished_at = now(), error = %s"
                " WHERE run_id = %s",
                (f"{type(exc).__name__}: {exc}"[:2000], run_id),
            )
            raise
        log_conn.execute(
            "UPDATE ops.job_runs SET status = 'ok', finished_at = now(), rows_out = %s"
            " WHERE run_id = %s",
            (run.rows_out, run_id),
        )
