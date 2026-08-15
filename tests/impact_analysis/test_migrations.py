from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "sql" / "tables"


EXPECTED = {
    25: "repository_snapshots",
    26: "repository_source_files",
    27: "repository_source_symbols",
    28: "repository_source_edges",
    29: "repository_source_chunks",
    30: "impact_analysis_runs",
    31: "impact_requirements",
    32: "impact_evidence",
    33: "impact_findings",
    34: "analysis_score_history",
    35: "generated_changes",
    36: "generated_change_validations",
}


def test_impact_table_migrations_are_numbered_and_idempotent() -> None:
    for number, table in EXPECTED.items():
        matches = list(TABLES.glob(f"{number:02d}_*.sql"))
        assert len(matches) == 1
        sql = matches[0].read_text(encoding="utf-8").lower()
        assert f"create table if not exists public.{table}" in sql
        assert "create index if not exists" in sql
        assert "alembic" not in sql


def test_source_chunks_have_exact_provenance_and_both_search_indexes() -> None:
    sql = (TABLES / "29_repository_source_chunks.sql").read_text(encoding="utf-8").lower()
    for column in (
        "snapshot_id",
        "file_id",
        "symbol_id",
        "start_line",
        "end_line",
        "content_sha256",
    ):
        assert column in sql
    assert "tsvector generated always" in sql
    assert "using gin(search_vector)" in sql
    assert "using hnsw (embedding vector_cosine_ops)" in sql


def test_run_and_finding_statuses_include_required_state_models() -> None:
    runs = (TABLES / "30_impact_analysis_runs.sql").read_text(encoding="utf-8")
    findings = (TABLES / "33_impact_findings.sql").read_text(encoding="utf-8")
    for value in ("QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"):
        assert value in runs
    for value in ("PRESENT", "PARTIAL", "MISSING", "UNKNOWN"):
        assert value in findings
    assert "status = 'UNKNOWN' and completion is null" in findings


def test_security_uses_project_membership_and_disables_anon_access() -> None:
    sql = (ROOT / "sql" / "impact_analysis_security.sql").read_text(
        encoding="utf-8"
    ).lower()
    for table in EXPECTED.values():
        assert f"alter table public.{table} enable row level security" in sql
    assert "is_project_member" in sql
    assert "from anon" in sql
