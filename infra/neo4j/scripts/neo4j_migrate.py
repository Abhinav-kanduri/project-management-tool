from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from neo4j import GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

from neo4j_settings import NEO4J_ROOT, load_settings

MIGRATION_PATTERN = re.compile(r"^(V(?P<number>\d+))__(?P<description>.+)\.cypher$")


@dataclass(frozen=True)
class Migration:
    version: str
    number: int
    path: Path
    checksum: str
    statements: tuple[str, ...]


def parse_cypher_statements(content: str) -> list[str]:
    """Split Cypher safely while discarding comments outside quoted values."""
    statements: list[str] = []
    current: list[str] = []
    state = "normal"
    index = 0

    while index < len(content):
        char = content[index]
        following = content[index + 1] if index + 1 < len(content) else ""

        if state == "line_comment":
            if char in "\r\n":
                current.append(char)
                state = "normal"
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and following == "/":
                current.append(" ")
                state = "normal"
                index += 2
            else:
                if char in "\r\n":
                    current.append(char)
                index += 1
            continue
        if state == "normal":
            if char == "/" and following == "/":
                state = "line_comment"
                index += 2
                continue
            if char == "/" and following == "*":
                state = "block_comment"
                index += 2
                continue
            if char == ";":
                statement = "".join(current).strip()
                if statement:
                    statements.append(statement)
                current = []
                index += 1
                continue
            if char in "'\"`":
                state = {"'": "single", '"': "double", "`": "backtick"}[char]
            current.append(char)
            index += 1
            continue

        delimiter = {"single": "'", "double": '"', "backtick": "`"}[state]
        current.append(char)
        if char == "\\" and following:
            current.append(following)
            index += 2
            continue
        if char == delimiter:
            if following == delimiter:
                current.append(following)
                index += 2
                continue
            state = "normal"
        index += 1

    if state in {"single", "double", "backtick", "block_comment"}:
        raise ValueError(f"Unterminated {state.replace('_', ' ')} in Cypher migration")
    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def discover_migrations(directory: Path) -> list[Migration]:
    migrations: list[Migration] = []
    versions: set[str] = set()
    for path in directory.glob("V*.cypher"):
        match = MIGRATION_PATTERN.fullmatch(path.name)
        if not match:
            raise ValueError(f"Invalid migration filename: {path.name}")
        version = match.group(1)
        if version in versions:
            raise ValueError(f"Duplicate migration version: {version}")
        versions.add(version)
        content = path.read_text(encoding="utf-8")
        statements = tuple(parse_cypher_statements(content))
        if not statements:
            raise ValueError(f"Migration contains no statements: {path.name}")
        migrations.append(
            Migration(
                version=version,
                number=int(match.group("number")),
                path=path,
                checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                statements=statements,
            )
        )
    return sorted(migrations, key=lambda migration: migration.number)


def applied_migrations(driver, database: str) -> dict[str, dict]:
    records, _, _ = driver.execute_query(
        "MATCH (m:GraphMigration) RETURN m.version AS version, "
        "m.filename AS filename, m.checksum AS checksum, m.applied_at AS applied_at "
        "ORDER BY m.version",
        database_=database,
    )
    return {record["version"]: record.data() for record in records}


def apply_migration(driver, database: str, migration: Migration) -> float:
    started = time.perf_counter()

    def run(transaction) -> None:
        for statement in migration.statements:
            transaction.run(statement).consume()

    with driver.session(database=database) as session:
        session.execute_write(run)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    driver.execute_query(
        "CREATE (:GraphMigration {version: $version, filename: $filename, "
        "checksum: $checksum, applied_at: datetime(), execution_time_ms: $elapsed_ms})",
        version=migration.version,
        filename=migration.path.name,
        checksum=migration.checksum,
        elapsed_ms=elapsed_ms,
        database_=database,
    )
    return time.perf_counter() - started


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run versioned Neo4j Cypher migrations.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--migrations-dir", type=Path, default=NEO4J_ROOT / "migrations"
    )
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
        migrations = discover_migrations(args.migrations_dir.resolve())
        if not migrations:
            raise RuntimeError("No Neo4j migrations were found.")
        driver = GraphDatabase.driver(
            settings.uri, auth=(settings.username, settings.password)
        )
        try:
            driver.verify_connectivity()
            applied = applied_migrations(driver, settings.database)
            failed = False
            pending: list[Migration] = []
            for migration in migrations:
                existing = applied.get(migration.version)
                if existing and existing["checksum"] != migration.checksum:
                    print(
                        f"ERROR {migration.version}: checksum differs from the applied migration.",
                        file=sys.stderr,
                    )
                    failed = True
                elif existing:
                    print(f"APPLIED {migration.version} {migration.path.name}")
                else:
                    pending.append(migration)
                    print(f"PENDING {migration.version} {migration.path.name}")
            if failed:
                return 2
            if args.status or args.dry_run:
                print(f"Summary: {len(applied)} applied, {len(pending)} pending")
                return 0
            for migration in pending:
                duration = apply_migration(driver, settings.database, migration)
                print(f"MIGRATED {migration.version} in {duration:.3f}s")
            print(
                f"Migration complete: {len(pending)} applied, "
                f"{len(migrations) - len(pending)} skipped"
            )
            return 0
        finally:
            driver.close()
    except (OSError, ValueError, RuntimeError, DriverError, Neo4jError) as error:
        print(f"Neo4j migration failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
