from pathlib import Path

from app.config import Settings
from app.services.scanner import RepositoryScanner


def test_scanner_prioritizes_readme_and_code(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Example\nArchitecture", encoding="utf-8")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\x00")

    scanner = RepositoryScanner(
        Settings(
            max_summary_files=10,
            max_total_summary_characters=100000,
            max_file_characters=50000,
        )
    )
    snapshot = scanner.scan(tmp_path)
    paths = [item.path for item in snapshot.files]
    assert "README.md" in paths
    assert "app/main.py" in paths
    assert ".env" not in paths
    python_file = next(item for item in snapshot.files if item.path == "app/main.py")
    assert any("def health" in item for item in python_file.outline)
