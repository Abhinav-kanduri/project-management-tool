from __future__ import annotations

import argparse
import sys
import time

from neo4j import GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

from neo4j_settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait until Neo4j accepts Bolt connections.")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    settings = load_settings()
    deadline = time.monotonic() + args.timeout
    delay = 1.0
    attempts = 0
    while time.monotonic() < deadline:
        attempts += 1
        driver = GraphDatabase.driver(
            settings.uri, auth=(settings.username, settings.password)
        )
        try:
            driver.verify_connectivity()
            print(f"Neo4j is ready after {attempts} attempt(s).")
            return 0
        except (DriverError, Neo4jError):
            pass
        finally:
            driver.close()
        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)
    print(f"Neo4j did not become ready within {args.timeout:.0f}s.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
