from uuid import uuid4

from app.impact_analysis.services.source_indexer import SourceIndexer


def test_coverage_uses_eligible_source_files_not_all_repository_files(tmp_path) -> None:
    (tmp_path / "app.py").write_text("def run():\n    return True\n", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"not-source")
    vendor = tmp_path / "node_modules"
    vendor.mkdir()
    (vendor / "package.js").write_text("ignored", encoding="utf-8")

    class Repository:
        def replace(self, snapshot_id, files):
            assert [item.path for item in files] == ["app.py"]
            return {"files": 1, "symbols": 1, "edges": 0, "chunks": 1}

    result = SourceIndexer(repository=Repository()).index_root(
        snapshot_id=uuid4(), root=tmp_path
    )
    assert result.discovered_files == 3
    assert result.indexed_files == 1
    assert result.skipped_files == 0
    assert result.coverage_percent == 100
