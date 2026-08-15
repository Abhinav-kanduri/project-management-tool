from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routes import chat


class SummaryCursor:
    def __init__(self, *, document=None, chunks=None):
        self.document = document
        self.chunks = chunks or []
        self.statements = []
        self.current = ""

    def execute(self, statement, parameters):
        self.current = statement
        self.statements.append((statement, parameters))

    def fetchone(self):
        if "from github_repository_summary_documents" in self.current:
            return self.document
        return None

    def fetchall(self):
        if "from github_repository_summary_chunks" in self.current:
            return self.chunks
        return []


def document():
    return {
        "id": uuid4(),
        "repository_url": "https://github.com/example/support-api",
        "repository_full_name": "example/support-api",
        "branch": "feature/summary",
        "commit_sha": "a" * 40,
        "generated_at": "2026-08-09T00:00:00Z",
        "indexed_at": "2026-08-09T00:01:00Z",
        "chunk_count": 2,
        "title": "Support API",
    }


def test_summary_grounding_queries_only_selected_document_vectors(monkeypatch) -> None:
    selected = document()
    chunk_id = uuid4()
    cursor = SummaryCursor(
        document=selected,
        chunks=[
            {
                "chunk_id": chunk_id,
                "chunk_index": 0,
                "heading_path": ["Architecture"],
                "section_title": "Architecture",
                "start_line": 10,
                "end_line": 20,
                "content": "The router delegates requests to the support service.",
                "score": 0.91,
            }
        ],
    )
    monkeypatch.setattr(
        chat,
        "client",
        SimpleNamespace(
            embeddings=SimpleNamespace(
                create=lambda **_kwargs: SimpleNamespace(
                    data=[
                        SimpleNamespace(
                            embedding=[0.1] * chat.OPENAI_EMBEDDING_DIMENSIONS
                        )
                    ]
                )
            )
        ),
    )

    context, sources, scope = chat.load_summary_grounding(
        cursor,
        uuid4(),
        "How are requests routed?",
        {
            "summary_document_id": str(selected["id"]),
            "branch": "feature/summary",
        },
    )

    sql = "\n".join(statement for statement, _ in cursor.statements)
    vector_parameters = cursor.statements[-1][1]
    assert "github_repository_summary_chunks" in sql
    assert "project_github_repositories" in sql
    assert "from features" not in sql
    assert "from user_stories" not in sql
    assert selected["id"] in vector_parameters
    assert "position(lower(c.section_title)" in sql
    assert context["chunks"][0]["content"].startswith("The router")
    assert sources[0]["source_type"] == "GITHUB_SUMMARY"
    assert sources[0]["source_id"] == str(chunk_id)
    assert scope["grounding_mode"] == "GITHUB_SUMMARY"
    assert scope["branch"] == "feature/summary"


def test_summary_grounding_never_falls_back_when_document_is_unauthorized(
    monkeypatch,
) -> None:
    cursor = SummaryCursor(document=None)

    with pytest.raises(HTTPException) as error:
        chat.load_summary_grounding(
            cursor,
            uuid4(),
            "What is implemented?",
            {"summary_document_id": str(uuid4())},
        )

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "SUMMARY_NOT_AVAILABLE"
    assert len(cursor.statements) == 1


def test_summary_chat_uses_supported_vector_retrieval_type() -> None:
    source = Path(chat.__file__).read_text(encoding="utf-8")
    schema = Path("sql/chat_conversation_schema.sql").read_text(encoding="utf-8")

    assert 'retrieval_type="VECTOR"' in source
    assert "'VECTOR'" in schema
    assert 'retrieval_type="SUMMARY_VECTOR"' not in source


def test_summary_answer_is_concise_and_uses_selected_summary_sections() -> None:
    answer = chat.format_summary_search_answer(
        "How are requests routed?",
        [
            {
                "source_key": "Architecture",
                "title": "Architecture",
                "snippet": "Requests pass through the router.",
            }
        ],
    )

    assert "From the selected branch summary" in answer
    assert "Requests pass through the router" in answer


def test_summary_answer_prefers_a_directly_requested_section() -> None:
    answer = chat.format_summary_search_answer(
        "Please give me the Executive Summary",
        [
            {
                "source_key": "Executive Summary",
                "title": "Executive Summary",
                "snippet": "This repository provides customer support automation.",
            },
            {
                "source_key": "Recommended Next Steps",
                "title": "Recommended Next Steps",
                "snippet": "This unrelated section should not be displayed.",
            },
        ],
    )

    assert answer.startswith("## Executive Summary")
    assert "customer support automation" in answer
    assert "unrelated section" not in answer


def test_summary_follow_up_retrieval_keeps_recent_question_context() -> None:
    query = chat.summary_retrieval_query(
        "Which of those are asynchronous?",
        ["Give me the list of repository functions"],
    )

    assert "list of repository functions" in query
    assert "Which of those are asynchronous?" in query
    assert (
        chat.summary_retrieval_query(
            "Explain the authentication architecture",
            ["Give me the list of repository functions"],
        )
        == "Explain the authentication architecture"
    )
