"""`python -m stream`: run the stream-worker; `python -m stream --once`: catch up once and exit."""

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import structlog

from airspace_common.log import configure_logging
from airspace_common.settings import StreamSettings
from stream.store import PgStore
from stream.worker import process_pending

log = structlog.get_logger()

CHANNEL = "new_snapshot"
# Re-check at least this often, in case a notification was missed.
RECHECK_SECONDS = 60
RECONNECT_SECONDS = 5
# Touched after every check; the container healthcheck fails when it is older than 3 minutes.
HEARTBEAT = Path("/tmp/stream-heartbeat")


def run_once(url: str) -> int:
    with psycopg.connect(url, autocommit=True) as conn:
        return process_pending(PgStore(conn), datetime.now(UTC))


def run_forever(url: str) -> None:
    while True:
        try:
            with (
                psycopg.connect(url, autocommit=True) as listen,
                psycopg.connect(url, autocommit=True) as work,
            ):
                listen.execute(f"LISTEN {CHANNEL}")
                log.info("stream_worker_connected")
                store = PgStore(work)
                while True:
                    process_pending(store, datetime.now(UTC))
                    HEARTBEAT.touch()
                    for _ in listen.notifies(timeout=RECHECK_SECONDS, stop_after=1):
                        pass
        except psycopg.OperationalError:
            log.warning("database_connection_lost", exc_info=True)
            time.sleep(RECONNECT_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(prog="stream")
    parser.add_argument("--once", action="store_true", help="process pending snapshots and exit")
    args = parser.parse_args()
    configure_logging("stream-worker")
    url = StreamSettings().database_url.get_secret_value()
    if args.once:
        log.info("stream_worker_once", snapshots=run_once(url))
    else:
        run_forever(url)


if __name__ == "__main__":
    main()
