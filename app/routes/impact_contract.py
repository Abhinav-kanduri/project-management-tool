from __future__ import annotations

import asyncio
import os
from ipaddress import ip_address
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import Field

from app.config import APP_ENV
from app.impact_analysis.graph.contract_view import ImpactGraphContractView
from app.impact_analysis.presenters import (
    present_evidence,
    present_finding,
    present_generated_change,
    present_requirement,
    present_run,
)
from app.impact_analysis.remediation.service import (
    ProviderNotConfiguredError,
    RemediationService,
)
from app.impact_analysis.remediation.prompt import RemediationPromptService
from app.impact_analysis.repositories.analysis import AnalysisRunNotFoundError
from app.impact_analysis.repositories.contract_queries import ImpactContractRepository
from app.impact_analysis.repositories.generated_change_views import (
    GeneratedChangeViewRepository,
)
from app.impact_analysis.repositories.generated_changes import (
    ChangeNotFoundError,
    ChangeStateError,
)
from app.impact_analysis.repositories.project_context import (
    ScopeAccessDeniedError,
    ScopeNotFoundError,
    ScopeValidationError,
)
from app.impact_analysis.repositories.results import AnalysisResultRepository
from app.impact_analysis.schemas import StartAnalysisRequest, StrictModel
from app.impact_analysis.services.analyzer import ImpactAnalysisService


router = APIRouter(prefix="/api/v1/impact-analysis", tags=["Impact Analysis"])
AnalysisActorHeader = Annotated[str | None, Header(alias="X-Actor")]
RemediationActor = Annotated[UUID, Header(alias="X-Actor")]
LOCAL_ANALYSIS_ACTOR = "local-impact-analysis"
ALLOW_LOCAL_ANONYMOUS_ANALYSIS = (
    APP_ENV != "production"
    and os.getenv("ALLOW_LOCAL_ANONYMOUS_IMPACT_ANALYSIS", "false").lower()
    in {"1", "true", "yes", "on"}
)


class ChangeDecision(StrictModel):
    decision: Literal["APPROVE", "REJECT"]
    comment: str = Field(default="", max_length=4000)


class RemediationPromptRequest(StrictModel):
    target: Literal["github_copilot_chat"] = "github_copilot_chat"
    target_repository: str | None = Field(default=None, max_length=255)
    target_ref: str | None = Field(default=None, max_length=255)
    include_related_requirements: bool = True
    include_test_plan: bool = True
    include_repository_warning: bool = True


def get_analysis_service() -> ImpactAnalysisService:
    return ImpactAnalysisService()


def get_remediation_service() -> RemediationService:
    return RemediationService()


def get_remediation_prompt_service() -> RemediationPromptService:
    return RemediationPromptService()


def process_analysis_in_background(
    *,
    service: ImpactAnalysisService,
    run_id: UUID,
    request: StartAnalysisRequest,
    package: Any,
) -> None:
    asyncio.run(
        service.process(run_id=run_id, request=request, package=package)
    )


def resolve_analysis_actor(
    request: Request, x_actor: AnalysisActorHeader = None
) -> str:
    if x_actor:
        try:
            return str(UUID(x_actor))
        except ValueError as error:
            raise _error(
                422,
                "INVALID_ANALYSIS_ACTOR",
                "X-Actor must be a valid authenticated user UUID.",
            ) from error
    client_host = request.client.host if request.client else ""
    try:
        is_loopback = ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = False
    if ALLOW_LOCAL_ANONYMOUS_ANALYSIS and is_loopback:
        return LOCAL_ANALYSIS_ACTOR
    raise _error(
        401,
        "AUTHENTICATED_ACTOR_REQUIRED",
        "Sign in with a user who is a member of the selected Project to continue.",
    )


AnalysisActor = Annotated[str, Depends(resolve_analysis_actor)]


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_analysis(
    request: StartAnalysisRequest,
    background_tasks: BackgroundTasks,
    x_actor: AnalysisActor,
) -> dict[str, Any]:
    service = get_analysis_service()
    try:
        row, package = service.start(request=request, actor=str(x_actor))
    except ScopeNotFoundError as error:
        raise _error(404, "INVALID_SCOPE", str(error)) from error
    except ScopeAccessDeniedError as error:
        raise _error(403, "ANALYSIS_ACCESS_DENIED", str(error)) from error
    except ScopeValidationError as error:
        raise _error(422, "INVALID_SCOPE", str(error)) from error
    if package is not None:
        background_tasks.add_task(
            process_analysis_in_background,
            service=service,
            run_id=row["id"],
            request=request,
            package=package,
        )
    return present_run(row)


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, x_actor: AnalysisActor) -> dict[str, Any]:
    return _read_run(run_id, x_actor)


@router.get("/runs/{run_id}/requirements")
def get_requirements(run_id: UUID, x_actor: AnalysisActor) -> dict[str, Any]:
    try:
        rows = ImpactContractRepository().requirements(run_id, actor=x_actor)
        return {"items": [present_requirement(row) for row in rows]}
    except AnalysisRunNotFoundError as error:
        raise _error(404, "ANALYSIS_NOT_FOUND", "Impact analysis run not found.") from error
    except PermissionError as error:
        raise _error(403, "ANALYSIS_ACCESS_DENIED", str(error)) from error


@router.get("/runs/{run_id}/observability")
def get_observability(run_id: UUID, x_actor: AnalysisActor) -> dict[str, Any]:
    try:
        return ImpactContractRepository().observability(run_id, actor=x_actor)
    except AnalysisRunNotFoundError as error:
        raise _error(
            404, "ANALYSIS_NOT_FOUND", "Impact analysis run not found."
        ) from error
    except PermissionError as error:
        raise _error(403, "ANALYSIS_ACCESS_DENIED", str(error)) from error


@router.get("/runs/{run_id}/findings")
def get_findings(
    run_id: UUID,
    x_actor: AnalysisActor,
    finding_status: Annotated[
        Literal["PRESENT", "PARTIAL", "MISSING", "UNKNOWN"] | None,
        Query(alias="status"),
    ] = None,
    category: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    try:
        rows, total = ImpactContractRepository().findings(
            run_id,
            actor=x_actor,
            status=finding_status,
            category=category,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [present_finding(row) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
        }
    except AnalysisRunNotFoundError as error:
        raise _error(404, "ANALYSIS_NOT_FOUND", "Impact analysis run not found.") from error
    except PermissionError as error:
        raise _error(403, "ANALYSIS_ACCESS_DENIED", str(error)) from error


@router.get("/findings/{finding_id}")
def get_finding(finding_id: UUID, x_actor: AnalysisActor) -> dict[str, Any]:
    try:
        return present_finding(
            ImpactContractRepository().finding(finding_id, actor=x_actor)
        )
    except AnalysisRunNotFoundError as error:
        raise _error(404, "FINDING_NOT_FOUND", "Impact finding not found.") from error
    except PermissionError as error:
        raise _error(403, "FINDING_ACCESS_DENIED", str(error)) from error


@router.get("/findings/{finding_id}/evidence")
def get_finding_evidence(finding_id: UUID, x_actor: AnalysisActor) -> dict[str, Any]:
    try:
        rows = ImpactContractRepository().evidence(finding_id, actor=x_actor)
        return {"items": [present_evidence(row) for row in rows]}
    except AnalysisRunNotFoundError as error:
        raise _error(404, "FINDING_NOT_FOUND", "Impact finding not found.") from error
    except PermissionError as error:
        raise _error(403, "FINDING_ACCESS_DENIED", str(error)) from error


@router.get("/runs/{run_id}/graph")
def get_graph(
    run_id: UUID,
    x_actor: AnalysisActor,
    view: Literal["expected", "actual", "comparison"],
) -> dict[str, Any]:
    _read_run(run_id, x_actor)
    try:
        return ImpactGraphContractView().get(run_id=str(run_id), view=view)
    except Exception as error:
        raise _error(503, "GRAPH_UNAVAILABLE", str(error), retryable=True) from error


@router.get("/history")
def get_history(
    product_space_id: UUID,
    project_id: UUID,
    x_actor: AnalysisActor,
    scope_type: Literal["FEATURE", "USER_STORY"] | None = None,
    scope_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> dict[str, Any]:
    if (scope_type is None) != (scope_id is None):
        raise _error(
            422,
            "INVALID_SCOPE_FILTER",
            "scope_type and scope_id must be supplied together.",
        )
    try:
        rows, total = ImpactContractRepository().history(
            product_space_id=product_space_id,
            project_id=project_id,
            scope_type=scope_type,
            scope_id=scope_id,
            page=page,
            page_size=page_size,
            actor=x_actor,
        )
        return {
            "items": [present_run(row) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
        }
    except PermissionError as error:
        raise _error(403, "ANALYSIS_ACCESS_DENIED", str(error)) from error
    except ValueError as error:
        raise _error(422, "PROJECT_OUTSIDE_PRODUCT_SPACE", str(error)) from error


@router.post("/runs/{run_id}/reanalyze", status_code=status.HTTP_202_ACCEPTED)
async def reanalyze(
    run_id: UUID,
    background_tasks: BackgroundTasks,
    x_actor: AnalysisActor,
) -> dict[str, Any]:
    previous = _read_run_row(run_id, x_actor)
    request = StartAnalysisRequest(
        product_space_id=previous["product_space_id"],
        project_id=previous["project_id"],
        release_id=previous["release_id"],
        scope_type=previous["scope_type"],
        scope_id=previous["scope_id"],
        project_repository_id=previous["project_repository_id"],
        ref=previous.get("branch") or previous.get("requested_ref"),
        force_repository_refresh=True,
        client_request_id=uuid4(),
    )
    service = get_analysis_service()
    row, package = service.start(request=request, actor=str(x_actor))
    if package is None:
        raise _error(409, "REANALYSIS_ALREADY_RUNNING", "Re-analysis already exists.")
    ImpactContractRepository().link_reanalysis(row["id"], run_id)
    background_tasks.add_task(
        process_analysis_in_background,
        service=service,
        run_id=row["id"],
        request=request,
        package=package,
    )
    return {
        "previous_run_id": str(run_id),
        "new_run_id": str(row["id"]),
        "status": row["status"],
    }


@router.get("/runs/{run_id}/comparison")
def compare_runs(
    run_id: UUID, baseline_run_id: UUID, x_actor: AnalysisActor
) -> dict[str, Any]:
    try:
        return ImpactContractRepository().comparison(
            run_id, baseline_run_id, actor=x_actor
        )
    except AnalysisRunNotFoundError as error:
        raise _error(404, "ANALYSIS_NOT_FOUND", str(error)) from error
    except PermissionError as error:
        raise _error(403, "ANALYSIS_ACCESS_DENIED", str(error)) from error
    except ValueError as error:
        raise _error(422, "INCOMPATIBLE_ANALYSIS_RUNS", str(error)) from error


@router.post(
    "/runs/{run_id}/findings/{finding_id}/remediation-prompt",
)
def generate_remediation_prompt(
    run_id: UUID,
    finding_id: UUID,
    request: RemediationPromptRequest,
    x_actor: AnalysisActor,
) -> dict[str, Any]:
    try:
        return get_remediation_prompt_service().generate(
            run_id=run_id,
            finding_id=finding_id,
            actor=x_actor,
            target_repository=request.target_repository,
            target_ref=request.target_ref,
            include_related_requirements=request.include_related_requirements,
            include_test_plan=request.include_test_plan,
            include_repository_warning=request.include_repository_warning,
        )
    except AnalysisRunNotFoundError as error:
        raise _error(
            404,
            "FINDING_NOT_FOUND",
            "The finding does not belong to the selected analysis run.",
        ) from error
    except PermissionError as error:
        raise _error(403, "FINDING_ACCESS_DENIED", str(error)) from error


@router.post(
    "/findings/{finding_id}/generated-changes",
    status_code=status.HTTP_202_ACCEPTED,
)
def request_change(finding_id: UUID, x_actor: RemediationActor) -> dict[str, Any]:
    service = get_remediation_service()
    if service.generator is None:
        raise _error(
            503,
            "CODE_GENERATION_NOT_CONFIGURED",
            "No trusted code-generation provider is configured.",
            retryable=False,
        )
    try:
        row = service.request(finding_id=finding_id, actor=x_actor)
        return _generated(row["id"], x_actor)
    except ChangeNotFoundError as error:
        raise _error(404, "FINDING_NOT_FOUND", "Impact finding not found.") from error
    except (ChangeStateError, ValueError) as error:
        raise _error(409, "GENERATED_CHANGE_NOT_ELIGIBLE", str(error)) from error


@router.get("/generated-changes/{change_id}")
def get_generated_change(change_id: UUID, x_actor: RemediationActor) -> dict[str, Any]:
    return _generated(change_id, x_actor)


@router.post("/generated-changes/{change_id}/validate")
def validate_generated_change(
    change_id: UUID, x_actor: RemediationActor
) -> dict[str, Any]:
    service = get_remediation_service()
    try:
        service.validate(change_id=change_id, actor=x_actor)
        return _generated(change_id, x_actor)
    except ProviderNotConfiguredError as error:
        raise _error(503, "VALIDATION_NOT_CONFIGURED", str(error)) from error
    except ChangeStateError as error:
        raise _error(409, "CHANGE_NOT_GENERATED", str(error)) from error


@router.post("/generated-changes/{change_id}/approve")
def approve_generated_change(
    change_id: UUID, request: ChangeDecision, x_actor: RemediationActor
) -> dict[str, Any]:
    try:
        get_remediation_service().decide(
            change_id=change_id,
            actor=x_actor,
            approved=request.decision == "APPROVE",
            comment=request.comment,
        )
        return _generated(change_id, x_actor)
    except ChangeStateError as error:
        raise _error(409, "VALIDATION_REQUIRED", str(error)) from error


@router.post("/generated-changes/{change_id}/pull-request")
async def create_pull_request(
    change_id: UUID, x_actor: RemediationActor
) -> dict[str, Any]:
    try:
        await get_remediation_service().publish(change_id=change_id, actor=x_actor)
        response = _generated(change_id, x_actor).get("pull_request")
        if response is None:
            raise RuntimeError("Pull request state was not persisted.")
        return response
    except ProviderNotConfiguredError as error:
        raise _error(503, "GITHUB_PUBLISHER_NOT_CONFIGURED", str(error)) from error
    except ChangeStateError as error:
        raise _error(409, "APPROVAL_REQUIRED", str(error)) from error


def _generated(change_id: UUID, actor: UUID) -> dict[str, Any]:
    try:
        return present_generated_change(
            GeneratedChangeViewRepository().get(change_id, actor=actor)
        )
    except ChangeNotFoundError as error:
        raise _error(404, "GENERATED_CHANGE_NOT_FOUND", "Generated change not found.") from error
    except PermissionError as error:
        raise _error(403, "GENERATED_CHANGE_ACCESS_DENIED", str(error)) from error


def _read_run(run_id: UUID, actor: UUID) -> dict[str, Any]:
    return present_run(_read_run_row(run_id, actor))


def _read_run_row(run_id: UUID, actor: UUID) -> dict[str, Any]:
    try:
        return AnalysisResultRepository().get_run(run_id, actor=str(actor))
    except AnalysisRunNotFoundError as error:
        raise _error(404, "ANALYSIS_NOT_FOUND", "Impact analysis run not found.") from error
    except PermissionError as error:
        raise _error(403, "ANALYSIS_ACCESS_DENIED", str(error)) from error


def _error(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "retryable": retryable},
    )
