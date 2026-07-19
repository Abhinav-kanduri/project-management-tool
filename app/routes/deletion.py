import hmac
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.config import ADMIN_RESET_TOKEN, APP_ENV, ENABLE_APPLICATION_DATA_RESET
from app.database import get_connection
from app.services.deletion import CascadeDeleteService

router = APIRouter(prefix="/api/v1", tags=["Deletion"])


class ResetRequest(BaseModel):
    confirmation: str
    environment: str


def _run(method: str, *args, actor: str):
    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                result = getattr(CascadeDeleteService(cursor, actor), method)(*args)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise


@router.get("/features/{feature_id}/deletion-preview")
def feature_deletion_preview(feature_id: UUID, x_actor: str = Header("local-user")) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        dependencies = CascadeDeleteService(cursor, x_actor).feature_dependencies(feature_id)
    return {"entity_type": "FEATURE", "entity_id": str(feature_id), "dependencies": dependencies}


@router.delete("/user-stories/{story_id}")
def delete_user_story(story_id: UUID, x_actor: str = Header("local-user")) -> dict:
    return _run("delete_user_story", story_id, actor=x_actor)


@router.delete("/features/{feature_id}")
def delete_feature(feature_id: UUID, cascade: bool = Query(False), x_actor: str = Header("local-user")) -> dict:
    return _run("delete_feature", feature_id, cascade, actor=x_actor)


@router.delete("/sprints/{sprint_id}")
def delete_sprint(sprint_id: UUID, x_actor: str = Header("local-user")) -> dict:
    return _run("delete_sprint", sprint_id, actor=x_actor)


@router.delete("/releases/{release_id}")
def delete_release(release_id: UUID, cascade: bool = Query(False), x_actor: str = Header("local-user")) -> dict:
    return _run("delete_release", release_id, cascade, actor=x_actor)


@router.delete("/projects/{project_id}")
def delete_project(project_id: UUID, cascade: bool = Query(False), x_actor: str = Header("local-user")) -> dict:
    return _run("delete_project", project_id, cascade, actor=x_actor)


@router.delete("/product-spaces/{space_id}")
def delete_product_space(space_id: UUID, cascade: bool = Query(False), x_actor: str = Header("local-user")) -> dict:
    return _run("delete_product_space", space_id, cascade, actor=x_actor)


@router.delete("/organizations/{organization_id}")
def delete_organization(organization_id: UUID, cascade: bool = Query(False), x_actor: str = Header("local-user")) -> dict:
    return _run("delete_organization", organization_id, cascade, actor=x_actor)


@router.delete("/admin/application-data")
def reset_application_data(request: ResetRequest, x_admin_token: str | None = Header(None),
                           x_actor: str = Header("unknown")) -> dict:
    if not ENABLE_APPLICATION_DATA_RESET or APP_ENV.lower() == "production":
        raise HTTPException(404, "Application data reset is disabled.")
    if not ADMIN_RESET_TOKEN or not x_admin_token or not hmac.compare_digest(x_admin_token, ADMIN_RESET_TOKEN):
        raise HTTPException(403, "Platform administrator authorization required.")
    if request.confirmation != "DELETE ALL RELEASELENS DATA":
        raise HTTPException(422, "Confirmation text does not match.")
    if request.environment != APP_ENV:
        raise HTTPException(422, "Environment confirmation does not match.")
    counts = _run("reset_application_data", actor=x_actor)
    return {"reset": True, "environment": APP_ENV, "deleted_counts": counts}
