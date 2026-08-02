from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from neo4j_settings import NEO4J_ROOT, REPOSITORY_ROOT

COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(NEO4J_ROOT / ".env"),
    "-f",
    str(NEO4J_ROOT / "compose.yaml"),
]
EXPECTED_VOLUMES = {"neo4j_data", "neo4j_logs", "neo4j_plugins"}


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset only local ReleaseLens Neo4j data.")
    parser.add_argument("--yes-delete-all-local-neo4j-data", action="store_true")
    args = parser.parse_args()
    if not args.yes_delete_all_local_neo4j_data:
        print(
            "Refusing destructive reset. Pass --yes-delete-all-local-neo4j-data.",
            file=sys.stderr,
        )
        return 2
    try:
        result = subprocess.run(
            [*COMPOSE, "config", "--volumes"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        configured = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        if configured != EXPECTED_VOLUMES:
            raise RuntimeError(
                f"Unexpected Compose volume set {sorted(configured)}; reset aborted."
            )
        print("DESTRUCTIVE: removing only ReleaseLens Neo4j Compose volumes.")
        run([*COMPOSE, "down", "--volumes"])
        run([*COMPOSE, "up", "-d"])
        python = sys.executable
        scripts = Path(__file__).resolve().parent
        run([python, str(scripts / "wait_for_neo4j.py")])
        run([python, str(scripts / "neo4j_migrate.py")])
        run([python, str(scripts / "neo4j_verify.py")])
        return 0
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"Neo4j reset failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
