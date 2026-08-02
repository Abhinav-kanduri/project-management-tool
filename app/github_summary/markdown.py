from __future__ import annotations

from app.github_summary.models import (
    ApiEndpointSummary,
    RepositoryIdentity,
    RepositorySummary,
)


NOT_IDENTIFIED = "Not identified from the analyzed repository files."


def render_repository_summary_markdown(
    repository: RepositoryIdentity,
    summary: RepositorySummary,
) -> str:
    lines = [
        "# Repository Summary",
        "",
        "## Repository Information",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Repository | [{repository.full_name}]({repository.url}) |",
        f"| Generated title | {summary.title.replace('|', '&#124;')} |",
        f"| Default branch | `{repository.default_branch}` |",
        f"| Analyzed branch/ref | `{repository.analyzed_ref}` |",
        f"| Commit SHA | `{repository.commit_sha or 'unknown'}` |",
        f"| Visibility | {repository.visibility or NOT_IDENTIFIED} |",
        f"| Archived | {'Yes' if repository.archived else 'No'} |",
        f"| Stars | {repository.stars} |",
        f"| Forks | {repository.forks} |",
        f"| Open issues | {repository.open_issues} |",
    ]
    _text_section(lines, "Executive Summary", summary.executive_summary)
    _text_section(lines, "Problem Statement", summary.problem_statement)
    _list_section(lines, "Business Capabilities", summary.primary_capabilities)
    _list_section(lines, "Functional Capabilities", summary.primary_capabilities)
    _list_section(lines, "Architecture Overview", summary.architecture)
    _list_section(
        lines, "End-to-End Processing Flow", summary.request_or_processing_flow
    )
    _list_section(lines, "Technology Stack", summary.technology_stack)
    _list_section(
        lines,
        "Project Structure",
        [f"`{item}`" for item in summary.evidence_files],
    )

    lines.extend(["", "## Key Components", ""])
    if summary.key_components:
        for component in summary.key_components:
            paths = ", ".join(f"`{path}`" for path in component.paths)
            lines.append(f"- **{component.name}:** {component.responsibility} ({paths})")
    else:
        lines.append(NOT_IDENTIFIED)

    lines.extend(["", "## API Endpoints", ""])
    if summary.api_endpoints:
        lines.extend(_endpoint_markdown(item) for item in summary.api_endpoints)
    else:
        lines.append(NOT_IDENTIFIED)

    _list_section(lines, "Data and Storage", summary.data_and_storage)
    all_findings = (
        summary.primary_capabilities
        + summary.architecture
        + summary.technology_stack
        + summary.data_and_storage
        + summary.request_or_processing_flow
        + summary.setup_and_run
        + summary.strengths
        + summary.risks_and_gaps
    )
    _list_section(
        lines,
        "AI, RAG, and Agentic Capabilities",
        _matching_findings(
            all_findings,
            ("ai", "rag", "llm", "openai", "embedding", "vector", "agent"),
        ),
    )
    _list_section(
        lines,
        "Security and Guardrails",
        _matching_findings(
            all_findings,
            (
                "security",
                "auth",
                "token",
                "secret",
                "permission",
                "redact",
                "guardrail",
            ),
        ),
    )
    _list_section(
        lines,
        "Configuration",
        _matching_findings(
            summary.setup_and_run + summary.technology_stack,
            ("config", "environment", ".env", "setting"),
        ),
    )
    _list_section(lines, "Local Setup", summary.setup_and_run)
    _list_section(
        lines,
        "Deployment",
        _matching_findings(
            summary.setup_and_run + summary.architecture + summary.technology_stack,
            ("docker", "deploy", "kubernetes", "cloud", "container", "production"),
        ),
    )
    _list_section(
        lines,
        "Testing",
        _matching_findings(
            summary.setup_and_run + summary.strengths + summary.risks_and_gaps,
            ("test", "pytest", "coverage", "spec"),
        ),
    )
    _list_section(
        lines,
        "Observability",
        _matching_findings(
            all_findings,
            ("log", "metric", "trace", "monitor", "health", "observability"),
        ),
    )
    _list_section(lines, "Strengths", summary.strengths)
    _list_section(lines, "Risks and Gaps", summary.risks_and_gaps)
    _list_section(lines, "Recommended Next Steps", summary.recommended_next_steps)
    _list_section(
        lines,
        "Evidence Files",
        [f"`{item}`" for item in summary.evidence_files],
    )
    return "\n".join(lines).strip() + "\n"


def _endpoint_markdown(endpoint: ApiEndpointSummary) -> str:
    source = f" (`{endpoint.source_file}`)" if endpoint.source_file else ""
    return f"- `{endpoint.method.upper()} {endpoint.path}` — {endpoint.purpose}{source}"


def _text_section(lines: list[str], title: str, content: str) -> None:
    lines.extend(["", f"## {title}", ""])
    lines.append(content.strip() or NOT_IDENTIFIED)


def _list_section(lines: list[str], title: str, items: list[str]) -> None:
    lines.extend(["", f"## {title}", ""])
    cleaned = [item.strip() for item in items if item and item.strip()]
    if cleaned:
        lines.extend(f"- {item}" for item in cleaned)
    else:
        lines.append(NOT_IDENTIFIED)


def _matching_findings(items: list[str], keywords: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for item in items:
        lowered = item.lower()
        if any(keyword in lowered for keyword in keywords) and item not in matches:
            matches.append(item)
    return matches
