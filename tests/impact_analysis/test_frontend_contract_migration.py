from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_reanalysis_lineage_migration_is_idempotent() -> None:
    sql = (ROOT / "sql" / "tables" / "37_impact_analysis_run_lineage.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "add column if not exists previous_run_id" in sql
    assert "references public.impact_analysis_runs(id)" in sql
    assert "create index if not exists" in sql
