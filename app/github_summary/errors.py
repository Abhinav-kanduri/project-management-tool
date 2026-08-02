from __future__ import annotations

from typing import Any


class SummaryApiError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        document_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.document_id = document_id
        self.details = details or {}

    def payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.document_id:
            error["document_id"] = self.document_id
        if self.details:
            error["details"] = self.details
        return {"error": error}


class SummaryConflictError(RuntimeError):
    pass


class SummaryDatabaseError(RuntimeError):
    pass


class SummaryArtifactError(RuntimeError):
    pass


class EmbeddingGenerationError(RuntimeError):
    pass

