"""Prints every panel query of the given dashboards as plain SQL, with Grafana's time macro
replaced, for infra/test-db.sh to run as grafana_reader. A query that fails there would fail in
Grafana too (missing grant, renamed column, syntax error)."""

import json
import re
import sys

MACRO = re.compile(r"\$__timeFilter\(([^)]+)\)")


def main(paths: list[str]) -> None:
    for path in paths:
        with open(path, encoding="utf-8") as f:
            dashboard = json.load(f)
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                sql = MACRO.sub(r"\1 > now() - interval '2 days'", target["rawSql"])
                if "$" in sql:
                    sys.exit(f"{path}: unhandled macro in panel {panel['title']!r}: {sql}")
                print(f"\echo {panel['title']}")
                print(f"{sql};")


if __name__ == "__main__":
    main(sys.argv[1:])
