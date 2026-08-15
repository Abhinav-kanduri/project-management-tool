from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException

from app.github_summary.github_client import GitHubApiError
from app.impact_analysis.schemas import (
    RepositoryBranchListResponse,
    RepositoryBranchSyncRequest,
    RepositoryBranchSyncResponse,
    RepositoryUnlinkResponse,
)
from app.impact_analysis.services.repository_branches import (
    RepositoryBranchService,
    RepositoryLinkHasDependencies,
)


router = APIRouter(prefix="/api/v1/github", tags=["GitHub Repository Summary"])
Actor = Annotated[UUID, Header(alias="X-Actor")]


@router.get(
    "/project-repositories/{project_repository_id}/branches",
    response_model=RepositoryBranchListResponse,
)
async def list_project_repository_branches(
    project_repository_id: UUID, x_actor: Actor
) -> RepositoryBranchListResponse:
    try:
        result = await RepositoryBranchService().list(
            project_repository_id=project_repository_id, actor=x_actor
        )
        return RepositoryBranchListResponse.model_validate(result)
    except LookupError as error:
        raise HTTPException(
            404,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": str(error)},
        ) from error
    except PermissionError as error:
        raise HTTPException(
            403,
            detail={"code": "REPOSITORY_OUTSIDE_PROJECT", "message": str(error)},
        ) from error
    except GitHubApiError as error:
        status_code = 429 if error.status_code == 429 else 502
        raise HTTPException(
            status_code,
            detail={
                "code": "GITHUB_RATE_LIMITED" if status_code == 429 else "GITHUB_UNAVAILABLE",
                "message": str(error),
                "retryable": True,
            },
        ) from error


@router.post(
    "/project-repositories/{project_repository_id}/sync",
    response_model=RepositoryBranchSyncResponse,
)
async def sync_project_repository_branch(
    project_repository_id: UUID,
    request: RepositoryBranchSyncRequest,
    x_actor: Actor,
) -> RepositoryBranchSyncResponse:
    try:
        result = await RepositoryBranchService().sync(
            project_repository_id=project_repository_id,
            actor=x_actor,
            branch=request.branch,
            force_refresh=request.force_refresh,
        )
        return RepositoryBranchSyncResponse.model_validate(result)
    except LookupError as error:
        raise HTTPException(
            404,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": str(error)},
        ) from error
    except PermissionError as error:
        raise HTTPException(
            403,
            detail={"code": "REPOSITORY_OUTSIDE_PROJECT", "message": str(error)},
        ) from error
    except GitHubApiError as error:
        status_code = 429 if error.status_code == 429 else 502
        raise HTTPException(
            status_code,
            detail={
                "code": "GITHUB_RATE_LIMITED" if status_code == 429 else "GITHUB_UNAVAILABLE",
                "message": str(error),
                "retryable": True,
            },
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            500,
            detail={"code": "REPOSITORY_SYNC_FAILED", "message": str(error)},
        ) from error


@router.delete(
    "/project-repositories/{project_repository_id}",
    response_model=RepositoryUnlinkResponse,
)
def unlink_project_repository(
    project_repository_id: UUID,
    x_actor: Actor,
) -> RepositoryUnlinkResponse:
    try:
        result = RepositoryBranchService().unlink(
            project_repository_id=project_repository_id,
            actor=x_actor,
        )
        return RepositoryUnlinkResponse.model_validate(result)
    except LookupError as error:
        raise HTTPException(
            404,
            detail={"code": "REPOSITORY_NOT_FOUND", "message": str(error)},
        ) from error
    except PermissionError as error:
        raise HTTPException(
            403,
            detail={"code": "REPOSITORY_UNLINK_FORBIDDEN", "message": str(error)},
        ) from error
    except RepositoryLinkHasDependencies as error:
        raise HTTPException(
            409,
            detail={
                "code": "REPOSITORY_LINK_HAS_DEPENDENCIES",
                "message": str(error),
                "dependencies": error.dependencies,
            },
        ) from error
