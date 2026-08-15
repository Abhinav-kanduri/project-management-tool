from __future__ import annotations

from decimal import Decimal
from typing import Any


ANALYSIS_PIPELINE = (
    ("SCOPE_RESOLUTION", "Resolve analysis scope", 0),
    ("DESIGN_CONTEXT", "Load design context", 8),
    ("REQUIREMENT_DECOMPOSITION", "Create atomic requirements", 15),
    ("EXPECTED_GRAPH", "Build expected architecture graph", 24),
    ("GITHUB_SNAPSHOT", "Pin GitHub commit", 34),
    ("SOURCE_PARSING", "Parse repository source", 40),
    ("SOURCE_INDEXING", "Index symbols and relationships", 48),
    ("ACTUAL_GRAPH", "Build actual implementation graph", 52),
    ("EVIDENCE_RETRIEVAL", "Compare requirements with evidence", 55),
    ("SCORING", "Calculate implementation score", 86),
    ("PERSISTING", "Persist findings", 92),
    ("COMPLETED", "Complete analysis", 100),
)


def number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float, Decimal)) else None


def present_timeline(row: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    run_status = str(row.get("status") or "QUEUED")
    current_stage = str(row.get("stage") or "SCOPE_RESOLUTION")
    progress = int(row.get("progress_percent") or 0)
    stage_names = [stage for stage, _, _ in ANALYSIS_PIPELINE]
    error_text = " ".join(
        str(row.get(field) or "") for field in ("error_code", "error_message")
    ).casefold()
    if current_stage == "FAILED" and any(
        marker in error_text
        for marker in (
            "repository_source_edges",
            "repository_source_files",
            "repository_source_symbols",
            "repository_source_chunks",
        )
    ):
        current_index = stage_names.index("SOURCE_INDEXING")
    elif current_stage in stage_names:
        current_index = stage_names.index(current_stage)
    else:
        current_index = max(
            index
            for index, (_, _, threshold) in enumerate(ANALYSIS_PIPELINE)
            if threshold <= progress
        )
    effective_stage = stage_names[current_index]
    timeline = []
    for index, (stage, label, threshold) in enumerate(ANALYSIS_PIPELINE):
        state = "PENDING"
        if run_status == "COMPLETED" or index < current_index:
            state = "COMPLETED"
        elif index == current_index:
            if run_status == "FAILED":
                state = "FAILED"
            elif run_status == "CANCELLED":
                state = "CANCELLED"
            else:
                state = "ACTIVE"
        item = {
            "stage": stage,
            "label": label,
            "status": state,
            "progress_percent": threshold,
        }
        if index == current_index and row.get("message"):
            item["message"] = row["message"]
        timeline.append(item)
    return timeline, effective_stage


def present_run(row: dict[str, Any]) -> dict[str, Any]:
    scope_key = row.get("feature_key") or row.get("story_key")
    scope_title = row.get("feature_title") or row.get("story_title")
    repository = None
    if row.get("snapshot_id") and row.get("commit_sha"):
        repository = {
            "repository_id": str(row["project_repository_id"]),
            "name": row["repository_name"],
            "branch": row["branch"],
            "commit_sha": row["commit_sha"],
        }
    timeline, effective_stage = present_timeline(row)
    error = None
    if row.get("error_code") or row.get("error_message"):
        error = {
            "code": row.get("error_code") or "ANALYSIS_FAILED",
            "message": row.get("error_message") or "Analysis failed",
            "stage": effective_stage,
        }
    return {
        "run_id": str(row["id"]),
        "status": row["status"],
        "stage": row["stage"],
        "progress_percent": row["progress_percent"],
        "message": row.get("message"),
        "timeline": timeline,
        "error": error,
        "created_at": row.get("created_at"),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "score": number(row.get("score")),
        "scope": (
            {
                "type": row["scope_type"],
                "id": str(row["scope_id"]),
                "key": scope_key,
                "title": scope_title,
            }
            if scope_key or scope_title else None
        ),
        "repository": repository,
        "counts": {
            "present": row.get("present_count", 0),
            "partial": row.get("partial_count", 0),
            "missing": row.get("missing_count", 0),
            "unknown": row.get("unknown_count", 0),
        },
        "previous_run_id": (
            str(row["previous_run_id"]) if row.get("previous_run_id") else None
        ),
    }


def present_requirement(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": row["requirement_id"],
        "text": row["text"],
        "type": row["type"],
        "weight": number(row.get("weight")),
        "status": row.get("status"),
    }


def present_finding(row: dict[str, Any]) -> dict[str, Any]:
    impacts = row.get("impacts") or []
    impact = " ".join(
        item.get("summary", "") for item in impacts if isinstance(item, dict)
    ).strip() or None
    return {
        "finding_id": str(row["id"]),
        "requirement_id": row["requirement_id"],
        "requirement": row["requirement"],
        "category": row["category"],
        "status": row["status"],
        "what_present": row.get("what_present") or None,
        "what_missing": row.get("what_missing") or None,
        "reason_code": row.get("reason_code"),
        "technical_reason": row.get("technical_reason"),
        "explanation": row.get("explanation"),
        "impact": impact,
        "recommendation": row.get("recommendation"),
        "confidence": number(row.get("confidence")),
        "weight": number(row.get("weight")),
        "completion": number(row.get("completion")),
        "score_contribution": number(row.get("score_contribution")),
        "evidence_count": int(row.get("evidence_count") or 0),
        "code_generation_available": bool(row.get("code_generation_available")),
        "predicate_results": row.get("predicate_results") or [],
        "model_name": row.get("model_name"),
        "prompt_version": row.get("prompt_version"),
        "evaluation_metadata": row.get("metadata") or {},
    }


def present_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": str(row["evidence_id"]),
        "type": row["type"],
        "repository": row.get("repository"),
        "commit_sha": row.get("commit_sha"),
        "file_path": row.get("file_path"),
        "symbol": row.get("symbol"),
        "start_line": row.get("start_line"),
        "end_line": row.get("end_line"),
        "document_id": row.get("document_id"),
        "document_name": row.get("document_name"),
        "section": row.get("section"),
        "retrieval_method": row.get("retrieval_method"),
        "retrieval_methods": (row.get("metadata") or {}).get(
            "retrieval_methods", []
        ),
        "supports": row.get("supports"),
        "direction": row.get("direction"),
        "rank": row.get("rank"),
        "score": number(row.get("score")),
        "description": row["description"],
        "excerpt": row.get("excerpt"),
        "metadata": row.get("metadata") or {},
    }


def present_generated_change(row: dict[str, Any]) -> dict[str, Any]:
    validations = row.get("validations") or []
    checks = [
        {
            "name": item["check_type"].casefold().replace("_", "-"),
            "status": item["status"],
            "duration_ms": None,
            "summary": item.get("log_excerpt"),
            "details_url": item.get("artifact_ref"),
        }
        for item in validations
    ]
    status = "QUEUED" if row["status"] == "REQUESTED" else row["status"]
    validation_status = "NOT_STARTED"
    if checks:
        validation_status = (
            "PASSED" if status in {"VALIDATED", "APPROVED", "PR_CREATED", "MERGED"}
            else "FAILED" if status == "VALIDATION_FAILED" else "RUNNING"
        )
    approval = None
    if row.get("approved_at"):
        approval = {
            "decision": "APPROVE" if row["status"] not in {"REJECTED"} else "REJECT",
            "actor": row.get("approved_by"),
            "comment": row.get("approval_comment"),
            "decided_at": row.get("approved_at"),
        }
    pull_request = None
    if row.get("pull_request_url"):
        pull_request = {
            "number": row.get("pull_request_number"),
            "url": row["pull_request_url"],
            "title": row.get("pull_request_title"),
            "state": "MERGED" if row["status"] == "MERGED" else "OPEN",
            "draft": row["status"] != "MERGED",
            "head": row.get("branch_name"),
            "base": row.get("base_ref"),
            "merged_at": row.get("merged_at"),
        }
    files = []
    for item in row.get("proposed_files") or []:
        files.append(
            {
                "path": item["path"],
                "status": item.get("status") or item.get("action"),
                "additions": item.get("additions"),
                "deletions": item.get("deletions"),
                "diff": item.get("diff"),
            }
        )
    return {
        "change_id": str(row["id"]),
        "finding_id": str(row["finding_id"]),
        "status": status,
        "repository": row.get("repository_name"),
        "base_ref": row.get("base_ref") or row.get("branch"),
        "base_commit_sha": row.get("base_commit_sha"),
        "created_at": row.get("created_at"),
        "files": files,
        "diff": row.get("patch"),
        "validation": {"status": validation_status, "checks": checks},
        "approval": approval,
        "pull_request": pull_request,
    }
