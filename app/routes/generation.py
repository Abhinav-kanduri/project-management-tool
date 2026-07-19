import logging
import json
from uuid import UUID
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from openai import OpenAIError
from pydantic import BeforeValidator

from app.document_reader import source_text
from app.database import get_connection
from app.generation import generate_feature, generate_user_stories
from app.models import FeatureResponse, UserStoriesResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Generation"])


def empty_upload_to_none(value: object) -> object:
    """Swagger sends an unused optional file field as an empty string."""
    return None if value == "" else value


OptionalUpload = Annotated[
    UploadFile | None,
    BeforeValidator(empty_upload_to_none),
    File(description="Optional .txt, .md, .pdf, or .docx document"),
]


@router.post("/feature/generation", response_model=FeatureResponse)
async def feature_generation(
    product_space_id: UUID = Form(),
    project_id: UUID = Form(),
    pi_release_id: UUID = Form(),
    feature_id: UUID | None = Form(default=None),
    text: str | None = Form(default=None),
    file: OptionalUpload = None,
) -> FeatureResponse:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("""select 1 from projects p join releases r on r.project_id=p.id
          where p.id=%s and p.product_space_id=%s and r.id=%s and r.archived_at is null""",(project_id,product_space_id,pi_release_id))
        if not cursor.fetchone(): raise HTTPException(status_code=422,detail="The selected PI Release does not belong to this Project.")
    if feature_id:
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute("select * from features where id=%s and project_id=%s and archived_at is null",(feature_id,project_id));saved=cursor.fetchone()
            if not saved: raise HTTPException(status_code=422,detail="The selected Feature does not belong to this Project.")
            cursor.execute("select given_text,when_text,then_text from acceptance_criteria where feature_id=%s order by criteria_order",(feature_id,));criteria=cursor.fetchall()
        source=json.dumps({"regenerate_existing_feature":True,"key":saved["feature_key"],"title":saved["title"],"description":saved["description"],"problem_statement":saved["problem_statement"],"business_value":saved["business_value"],"functional_requirements":saved["functional_requirements"],"non_functional_requirements":saved["non_functional_requirements"],"acceptance_criteria":criteria,"dependencies":saved["dependencies"],"risks":saved["risks"],"assumptions":saved["assumptions"],"user_revision_instructions":text})
    else:
        source = await source_text(text, file)
    try:
        return generate_feature(source)
    except (OpenAIError, RuntimeError) as error:
        logger.exception("Feature generation failed")
        raise HTTPException(
            status_code=502, detail="The AI service could not generate the feature."
        ) from error


@router.post("/userstories/generation", response_model=UserStoriesResponse)
async def user_stories_generation(
    count: int = Form(ge=1, le=20),
    feature_id: UUID = Form(),
    project_id: UUID = Form(),
    product_space_id: UUID = Form(),
    pi_release_id: UUID = Form(),
    sprint_id: UUID | None = Form(default=None),
    additional_instructions: str | None = Form(default=None),
) -> UserStoriesResponse:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("""select f.*,r.name pi_name,r.start_date pi_start,r.target_date pi_end from features f
          join releases r on r.id=f.release_id where f.id=%s and f.archived_at is null""",(feature_id,));feature=cursor.fetchone()
        if not feature: raise HTTPException(status_code=404,detail="Unable to load the selected Feature.")
        if feature["project_id"]!=project_id or feature["product_space_id"]!=product_space_id: raise HTTPException(status_code=422,detail="The selected Feature does not belong to this Project.")
        if feature["release_id"]!=pi_release_id: raise HTTPException(status_code=422,detail="The selected PI Release does not match the parent Feature.")
        sprint_name=None
        if sprint_id:
            cursor.execute("select display_name,name from sprints where id=%s and project_id=%s and release_id=%s and archived_at is null",(sprint_id,project_id,pi_release_id));sprint=cursor.fetchone()
            if not sprint: raise HTTPException(status_code=422,detail="The selected Sprint does not belong to this Project and PI Release.")
            sprint_name=sprint["display_name"] or sprint["name"]
        cursor.execute("select given_text,when_text,then_text from acceptance_criteria where feature_id=%s order by criteria_order",(feature_id,));criteria=cursor.fetchall()
    if not feature["description"] and not feature["functional_requirements"]:
        raise HTTPException(status_code=422,detail="The selected Feature has no description or requirements to generate from.")
    source=json.dumps({"key":feature["feature_key"],"title":feature["title"],"description":feature["description"],"problem_statement":feature["problem_statement"],"business_value":feature["business_value"],"functional_requirements":feature["functional_requirements"],"non_functional_requirements":feature["non_functional_requirements"],"acceptance_criteria":criteria,"dependencies":feature["dependencies"],"risks":feature["risks"],"assumptions":feature["assumptions"],"priority":feature["priority"],"status":feature["status"],"pi_release":{"name":feature["pi_name"],"start":str(feature["pi_start"]),"end":str(feature["pi_end"])},"sprint":sprint_name,"additional_instructions":additional_instructions})
    try:
        return generate_user_stories(source, count)
    except (OpenAIError, RuntimeError) as error:
        logger.exception("User-story generation failed")
        raise HTTPException(
            status_code=502, detail="The AI service could not generate the user stories."
        ) from error
