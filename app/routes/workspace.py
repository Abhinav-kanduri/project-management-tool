import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from app.database import get_connection
from app.models import Feature, UserStory

router = APIRouter(prefix="/api/v1", tags=["Workspace"])


class SaveGeneratedItemsRequest(BaseModel):
    product_space_id: UUID
    project_id: UUID
    release_id: UUID | None = None
    sprint_id: UUID | None = None
    parent_feature_id: UUID | None = None
    save_mode: Literal["DRAFT", "BACKLOG", "SPRINT"] = "BACKLOG"
    input_prompt: str = Field(default="AI-generated work", max_length=100_000)
    feature: Feature | None = None
    user_stories: list[UserStory] = Field(default_factory=list, max_length=20)


class WorkItemCreate(BaseModel):
    item_type: Literal["FEATURE", "USER_STORY"]
    title: str = Field(min_length=3, max_length=500)
    description: str | None = Field(default=None, max_length=20_000)
    parent_feature_id: UUID | None = None
    status: str = Field(default="BACKLOG", pattern="^[A-Z_]+$")
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    story_points: int | None = Field(default=None, ge=1, le=100)
    pi_release_id: UUID | None = None


class GeneratePIYear(BaseModel):
    year: int = Field(ge=2000,le=2200)


class GenerateSprints(BaseModel):
    count: int = Field(default=6,ge=1,le=20)
    duration_days: int = Field(default=14,ge=1,le=60)


class RegeneratedFeatureSave(BaseModel):
    pi_release_id: UUID
    status: Literal["DRAFT","BACKLOG"]
    feature: Feature


class WorkItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=500)
    description: str | None = Field(default=None, max_length=20_000)
    status: str | None = Field(default=None, pattern="^[A-Z_]+$")
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None
    story_points: int | None = Field(default=None, ge=1, le=100)
    version: int = Field(ge=1)


class HierarchyInput(BaseModel):
    name: str = Field(min_length=2,max_length=200)
    key: str = Field(min_length=2,max_length=20,pattern="^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None,max_length=5000)


@router.post("/product-spaces",status_code=201)
def create_product_space(request: HierarchyInput) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select id from organizations order by created_at limit 1"); org=cursor.fetchone()
        cursor.execute("insert into product_spaces(organization_id,name,space_key,description) values(%s,%s,%s,%s) returning id",(org["id"],request.name,request.key.upper(),request.description)); item=cursor.fetchone(); connection.commit()
    return {"id":str(item["id"]),"message":"Product space created."}


@router.patch("/product-spaces/{space_id}")
def update_product_space(space_id: UUID,request: HierarchyInput) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("update product_spaces set name=%s,space_key=%s,description=%s,version=version+1,updated_at=now() where id=%s and archived_at is null returning id",(request.name,request.key.upper(),request.description,space_id))
        if not cursor.fetchone(): raise HTTPException(404,"Product space not found.")
        connection.commit()
    return {"message":"Product space saved."}


@router.delete("/product-spaces/{space_id}")
def delete_product_space(space_id: UUID) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select count(*) n from projects where product_space_id=%s",(space_id,)); count=cursor.fetchone()["n"]
        if count: raise HTTPException(409,f"This product space contains {count} projects. Move or archive them first.")
        cursor.execute("delete from product_spaces where id=%s returning id",(space_id,))
        if not cursor.fetchone(): raise HTTPException(404,"Product space not found.")
        connection.commit()
    return {"message":"Empty product space deleted."}


@router.post("/product-spaces/{space_id}/archive")
def archive_product_space(space_id: UUID) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select count(*) n from projects where product_space_id=%s and archived_at is null",(space_id,)); projects=cursor.fetchone()["n"]
        cursor.execute("update user_stories set archived_at=coalesce(archived_at,now()) where product_space_id=%s",(space_id,));cursor.execute("update features set archived_at=coalesce(archived_at,now()) where product_space_id=%s",(space_id,));cursor.execute("update projects set archived_at=coalesce(archived_at,now()) where product_space_id=%s",(space_id,));cursor.execute("update product_spaces set archived_at=coalesce(archived_at,now()) where id=%s returning id",(space_id,))
        if not cursor.fetchone(): raise HTTPException(404,"Product space not found.")
        connection.commit()
    return {"message":f"Product space and {projects} projects archived."}


@router.post("/product-spaces/{space_id}/projects",status_code=201)
def create_project(space_id: UUID,request: HierarchyInput) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select organization_id from product_spaces where id=%s and archived_at is null",(space_id,)); space=cursor.fetchone()
        if not space: raise HTTPException(404,"Product space not found.")
        cursor.execute("insert into projects(organization_id,product_space_id,project_key,name,description,owner_name) values(%s,%s,%s,%s,%s,'Abhinav') returning id",(space["organization_id"],space_id,request.key.upper(),request.name,request.description)); project=cursor.fetchone(); cursor.execute("insert into project_sequences(project_id) values(%s)",(project["id"],))
        year=2026
        for number in range(1,5):
            month=1+(number-1)*3;name=f"{year} PI {number}"
            cursor.execute("""insert into releases(organization_id,product_space_id,project_id,name,display_name,year,pi_number,start_date,target_date,status) values(%s,%s,%s,%s,%s,%s,%s,make_date(%s,%s,1),(make_date(%s,%s,1)+interval '3 months - 1 day')::date,'PLANNED')""",(space["organization_id"],space_id,project["id"],name,name,year,number,year,month,year,month))
        connection.commit()
    return {"id":str(project["id"]),"message":"Project created."}


@router.patch("/projects/{project_id}")
def update_project(project_id: UUID,request: HierarchyInput) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("update projects set name=%s,project_key=%s,description=%s,version=version+1,updated_at=now() where id=%s returning id",(request.name,request.key.upper(),request.description,project_id))
        if not cursor.fetchone(): raise HTTPException(404,"Project not found.")
        connection.commit()
    return {"message":"Project saved."}


@router.delete("/projects/{project_id}")
def delete_project(project_id: UUID) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select (select count(*) from features where project_id=%s)+(select count(*) from user_stories where project_id=%s) n",(project_id,project_id)); count=cursor.fetchone()["n"]
        if count: raise HTTPException(409,f"This project contains {count} work items. Archive them first.")
        cursor.execute("delete from sprints where project_id=%s",(project_id,));cursor.execute("delete from releases where project_id=%s",(project_id,));cursor.execute("delete from project_sequences where project_id=%s",(project_id,));cursor.execute("delete from projects where id=%s returning id",(project_id,))
        if not cursor.fetchone(): raise HTTPException(404,"Project not found.")
        connection.commit()
    return {"message":"Empty project deleted."}


@router.post("/projects/{project_id}/archive")
def archive_project(project_id: UUID) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select count(*) n from features where project_id=%s and archived_at is null",(project_id,)); features=cursor.fetchone()["n"];cursor.execute("select count(*) n from user_stories where project_id=%s and archived_at is null",(project_id,)); stories=cursor.fetchone()["n"]
        cursor.execute("update user_stories set archived_at=coalesce(archived_at,now()) where project_id=%s",(project_id,));cursor.execute("update features set archived_at=coalesce(archived_at,now()) where project_id=%s",(project_id,));cursor.execute("update projects set archived_at=coalesce(archived_at,now()) where id=%s returning id",(project_id,))
        if not cursor.fetchone(): raise HTTPException(404,"Project not found.")
        connection.commit()
    return {"message":f"Project, {features} features, and {stories} stories archived."}


@router.get("/workspace")
def workspace_context() -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select o.id organization_id, o.name organization_name,
                   ps.id product_space_id, ps.name product_space_name, ps.space_key, ps.description space_description,
                   p.id project_id, p.name project_name, p.project_key, p.owner_name, p.description project_description
            from organizations o
            join product_spaces ps on ps.organization_id=o.id and ps.archived_at is null
            left join projects p on p.product_space_id=ps.id and p.archived_at is null
            order by ps.name, p.name
            """
        )
        rows = cursor.fetchall()
        cursor.execute("select id,name from organizations order by created_at limit 1")
        organization=cursor.fetchone()
        cursor.execute("select id, project_id, name,display_name,year,pi_number,start_date,target_date,status from releases where archived_at is null and year is not null order by year,pi_number")
        releases = cursor.fetchall()
        cursor.execute("select id,project_id,release_id,name,display_name,sprint_number,start_date,end_date,status from sprints where archived_at is null order by release_id,sprint_number")
        sprints = cursor.fetchall()
    spaces: dict[str, dict] = {}
    for row in rows:
        key = str(row["product_space_id"])
        spaces.setdefault(key, {"id": key, "name": row["product_space_name"], "key":row["space_key"],"description":row["space_description"], "projects": []})
        if row["project_id"]:
            spaces[key]["projects"].append({
                "id": str(row["project_id"]), "name": row["project_name"],
                "key": row["project_key"], "owner": row["owner_name"],"description":row["project_description"],
            })
    return {
        "organization": {"id": str(organization["id"]), "name": organization["name"]} if organization else None,
        "product_spaces": list(spaces.values()),
        "releases": [{**row, "id": str(row["id"]), "project_id": str(row["project_id"])} for row in releases],
        "sprints": [{**row, "id": str(row["id"]), "project_id": str(row["project_id"]), "release_id": str(row["release_id"]) if row["release_id"] else None} for row in sprints],
    }


@router.post("/projects/{project_id}/pi-releases/generate-year")
def generate_pi_year(project_id: UUID,request: GeneratePIYear) -> dict:
    created=[];existing=[]
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select organization_id,product_space_id from projects where id=%s",(project_id,));project=cursor.fetchone()
        if not project: raise HTTPException(404,"Project not found.")
        for number in range(1,5):
            name=f"{request.year} PI {number}";month=1+(number-1)*3
            cursor.execute("select id from releases where project_id=%s and year=%s and pi_number=%s",(project_id,request.year,number))
            if cursor.fetchone(): existing.append(name);continue
            cursor.execute("""insert into releases(organization_id,product_space_id,project_id,name,display_name,year,pi_number,start_date,target_date,status)
              values(%s,%s,%s,%s,%s,%s,%s,make_date(%s,%s,1),(make_date(%s,%s,1)+interval '3 months - 1 day')::date,'PLANNED')""",(project["organization_id"],project["product_space_id"],project_id,name,name,request.year,number,request.year,month,request.year,month));created.append(name)
        connection.commit()
    return {"created":created,"existing":existing,"message":f"{len(created)} PI Releases created; {len(existing)} already existed."}


@router.post("/projects/{project_id}/pi-releases/{pi_release_id}/generate-sprints")
def generate_pi_sprints(project_id: UUID,pi_release_id: UUID,request: GenerateSprints) -> dict:
    created=[];existing=[]
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select r.*,p.organization_id,p.product_space_id from releases r join projects p on p.id=r.project_id where r.id=%s and r.project_id=%s and r.archived_at is null",(pi_release_id,project_id));pi=cursor.fetchone()
        if not pi: raise HTTPException(422,"The selected PI Release does not belong to this Project.")
        for number in range(1,request.count+1):
            display=f"{pi['display_name'] or pi['name']} · Sprint {number}";start=pi["start_date"]
            cursor.execute("select id from sprints where project_id=%s and release_id=%s and sprint_number=%s",(project_id,pi_release_id,number))
            if cursor.fetchone(): existing.append(display);continue
            cursor.execute("""insert into sprints(organization_id,product_space_id,project_id,release_id,sprint_number,name,display_name,status,start_date,end_date)
              values(%s,%s,%s,%s,%s,%s,%s,'PLANNED',%s+(%s*interval '1 day'),least(%s,(%s+(%s*interval '1 day')+((%s-1)*interval '1 day'))::date))""",(pi["organization_id"],pi["product_space_id"],project_id,pi_release_id,number,f"Sprint {number}",display,start,(number-1)*request.duration_days,pi["target_date"],start,(number-1)*request.duration_days,request.duration_days));created.append(display)
        connection.commit()
    return {"created":created,"existing":existing,"message":f"{len(created)} Sprints created; {len(existing)} already existed."}


@router.get("/product-spaces/{product_space_id}/overview")
def product_space_overview(product_space_id: UUID) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select id,name,description from product_spaces where id=%s and archived_at is null",(product_space_id,))
        space=cursor.fetchone()
        if not space: raise HTTPException(status_code=404,detail="Product space not found.")
        cursor.execute(
            """select p.id,p.name,p.project_key,p.owner_name,
               count(distinct f.id) filter(where f.archived_at is null) feature_count,
               count(distinct us.id) filter(where us.archived_at is null) story_count,
               count(distinct us.id) filter(where us.archived_at is null and us.status in ('READY','IN_PROGRESS','CODE_REVIEW','TESTING')) in_progress_count,
               count(distinct us.id) filter(where us.archived_at is null and us.status in ('DONE','COMPLETED')) completed_count,
               count(distinct us.id) filter(where us.archived_at is null and us.status in ('BACKLOG','DRAFT')) backlog_count,
               max(r.name) filter(where r.status='ACTIVE') current_release,
               max(s.name) filter(where s.status='ACTIVE') active_sprint
               from projects p left join features f on f.project_id=p.id
               left join user_stories us on us.project_id=p.id
               left join releases r on r.project_id=p.id
               left join sprints s on s.project_id=p.id
               where p.product_space_id=%s group by p.id order by p.name""",
            (product_space_id,),
        )
        projects=cursor.fetchall()
        cursor.execute(
            """select f.id,f.project_id,f.feature_key,f.title,f.status,f.priority,f.version,f.updated_at,
               count(us.id) filter(where us.archived_at is null) story_count,
               count(us.id) filter(where us.archived_at is null and us.status in ('DONE','COMPLETED')) completed_count
               from features f left join user_stories us on us.feature_id=f.id
               where f.product_space_id=%s and f.archived_at is null
               group by f.id order by f.created_at""",(product_space_id,))
        features=cursor.fetchall()
        cursor.execute(
            """select us.id,us.project_id,us.feature_id,us.story_key,us.title,us.status,us.priority,
               us.story_points,us.version,us.updated_at from user_stories us
               where us.product_space_id=%s and us.archived_at is null order by us.created_at""",(product_space_id,))
        stories=cursor.fetchall()
    stories_by_feature: dict[str,list]= {}
    for story in stories: stories_by_feature.setdefault(str(story["feature_id"]),[]).append(story)
    features_by_project: dict[str,list]= {}
    for feature in features:
        feature["user_stories"]=stories_by_feature.get(str(feature["id"]),[])
        features_by_project.setdefault(str(feature["project_id"]),[]).append(feature)
    for project in projects: project["features"]=features_by_project.get(str(project["id"]),[])
    totals={"projects":len(projects),"features":sum(p["feature_count"] for p in projects),"stories":sum(p["story_count"] for p in projects),"in_progress":sum(p["in_progress_count"] for p in projects),"completed":sum(p["completed_count"] for p in projects)}
    return {"product_space":space,"totals":totals,"projects":projects}


@router.get("/projects/{project_id}/backlog")
def project_backlog(project_id: UUID, piReleaseId: UUID | None = None,
                    featureId: UUID | None = None, sprintId: str | None = None,
                    userStoryId: UUID | None = None) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select * from projects where id=%s", (project_id,))
        project = cursor.fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found.")
        feature_sql=" and release_id=%s" if piReleaseId else ""; feature_args=[project_id]+([piReleaseId] if piReleaseId else [])
        if featureId: feature_sql+=" and id=%s"; feature_args.append(featureId)
        cursor.execute("""select id, release_id, feature_key, title, description, status, priority, version, created_at
               from features where project_id=%s and archived_at is null"""+feature_sql+" order by created_at desc",tuple(feature_args))
        features = cursor.fetchall()
        story_sql=""; story_args=[project_id]
        if piReleaseId: story_sql+=" and release_id=%s"; story_args.append(piReleaseId)
        if featureId: story_sql+=" and feature_id=%s"; story_args.append(featureId)
        if sprintId=="unassigned": story_sql+=" and sprint_id is null"
        elif sprintId: story_sql+=" and sprint_id=%s"; story_args.append(UUID(sprintId))
        if userStoryId: story_sql+=" and id=%s"; story_args.append(userStoryId)
        cursor.execute("""select id, release_id, feature_id, sprint_id, story_key, title, story_text, status, priority,
                      story_points, version, created_at from user_stories
               where project_id=%s and archived_at is null"""+story_sql+" order by created_at desc",tuple(story_args))
        stories = cursor.fetchall()
    return {"project": project, "features": features, "user_stories": stories}


@router.get("/projects/{project_id}/planning-hierarchy")
def planning_hierarchy(project_id: UUID, piReleaseId: UUID | None = None,
                       featureId: UUID | None = None, sprintId: str | None = None,
                       userStoryId: UUID | None = None) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select id,project_key,name from projects where id=%s and archived_at is null",(project_id,));project=cursor.fetchone()
        if not project: raise HTTPException(404,"Project not found.")
        pi_sql=" and id=%s" if piReleaseId else ""; pi_args=[project_id]+([piReleaseId] if piReleaseId else [])
        cursor.execute("select id,name,display_name,year,pi_number,start_date,target_date from releases where project_id=%s and year is not null and archived_at is null"+pi_sql+" order by year,pi_number",tuple(pi_args));pis=cursor.fetchall()
        feature_sql=" and release_id=%s" if piReleaseId else ""; feature_args=[project_id]+([piReleaseId] if piReleaseId else [])
        if featureId: feature_sql+=" and id=%s"; feature_args.append(featureId)
        cursor.execute("select id,release_id,feature_key,title,description,status,priority,updated_at from features where project_id=%s and archived_at is null"+feature_sql+" order by created_at",tuple(feature_args));features=cursor.fetchall()
        sprint_sql=" and release_id=%s" if piReleaseId else ""; sprint_args=[project_id]+([piReleaseId] if piReleaseId else [])
        if sprintId and sprintId!="unassigned": sprint_sql+=" and id=%s"; sprint_args.append(UUID(sprintId))
        cursor.execute("select id,release_id,sprint_number,name,display_name from sprints where project_id=%s and archived_at is null"+sprint_sql+" order by release_id,sprint_number",tuple(sprint_args));sprints=cursor.fetchall()
        story_sql=""; story_args=[project_id]
        if piReleaseId: story_sql+=" and release_id=%s"; story_args.append(piReleaseId)
        if featureId: story_sql+=" and feature_id=%s"; story_args.append(featureId)
        if sprintId=="unassigned": story_sql+=" and sprint_id is null"
        elif sprintId: story_sql+=" and sprint_id=%s"; story_args.append(UUID(sprintId))
        if userStoryId: story_sql+=" and id=%s"; story_args.append(userStoryId)
        cursor.execute("select id,release_id,feature_id,sprint_id,story_key,title,story_text,status,priority,story_points,updated_at from user_stories where project_id=%s and archived_at is null"+story_sql+" order by created_at",tuple(story_args));stories=cursor.fetchall()
    stories_by_feature:dict[str,list]={}
    for story in stories: stories_by_feature.setdefault(str(story["feature_id"]),[]).append(story)
    sprints_by_pi:dict[str,list]={}
    for sprint in sprints: sprints_by_pi.setdefault(str(sprint["release_id"]),[]).append(sprint)
    features_by_pi:dict[str,list]={}
    for feature in features:
        groups=[]
        feature_stories=stories_by_feature.get(str(feature["id"]),[])
        for sprint in sprints_by_pi.get(str(feature["release_id"]),[]): groups.append({**sprint,"stories":[s for s in feature_stories if s["sprint_id"]==sprint["id"]]})
        groups.append({"id":None,"sprint_number":None,"name":"Unassigned Sprint","display_name":"Unassigned Sprint","stories":[s for s in feature_stories if s["sprint_id"] is None]})
        feature["sprints"]=groups;feature["story_count"]=len(feature_stories);feature["completed_story_count"]=sum(s["status"] in ("DONE","COMPLETED") for s in feature_stories)
        features_by_pi.setdefault(str(feature["release_id"]),[]).append(feature)
    for pi in pis: pi["features"]=features_by_pi.get(str(pi["id"]),[])
    return {"project":project,"pi_releases":pis}


@router.get("/projects/{project_id}/planning-options")
def planning_options(project_id: UUID, piReleaseId: UUID | None = None, featureId: UUID | None = None, sprintId: str | None = None) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select id from projects where id=%s and archived_at is null", (project_id,))
        if not cursor.fetchone(): raise HTTPException(404, "Project not found.")
        cursor.execute("select id,name,display_name,year,pi_number,start_date,target_date from releases where project_id=%s and archived_at is null order by year,pi_number", (project_id,)); releases=cursor.fetchall()
        pi_sql=" and release_id=%s" if piReleaseId else ""; pi_args=[piReleaseId] if piReleaseId else []
        cursor.execute("select id,feature_key,title,status,release_id from features where project_id=%s and archived_at is null"+pi_sql+" order by feature_key", tuple([project_id]+pi_args)); features=cursor.fetchall()
        cursor.execute("select id,sprint_number,name,display_name,release_id from sprints where project_id=%s and archived_at is null"+pi_sql+" order by release_id,sprint_number", tuple([project_id]+pi_args)); sprints=cursor.fetchall()
        story_sql=pi_sql; story_args=[project_id]+pi_args
        if featureId: story_sql+=" and feature_id=%s"; story_args.append(featureId)
        if sprintId=="unassigned": story_sql+=" and sprint_id is null"
        elif sprintId:
            try: story_args.append(UUID(sprintId))
            except ValueError: raise HTTPException(422,"Invalid Sprint selection.")
            story_sql+=" and sprint_id=%s"
        cursor.execute("select id,story_key,title,feature_id,release_id,sprint_id from user_stories where project_id=%s and archived_at is null"+story_sql+" order by story_key",tuple(story_args)); stories=cursor.fetchall()
    return {"piReleases":releases,"features":features,"sprints":sprints,"userStories":stories}


@router.get("/features/{feature_id}/generation-context")
def feature_generation_context(feature_id: UUID) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("""select f.*,r.name pi_name,r.display_name pi_display_name,r.start_date pi_start_date,r.target_date pi_end_date
          from features f join releases r on r.id=f.release_id where f.id=%s and f.archived_at is null""",(feature_id,));feature=cursor.fetchone()
        if not feature: raise HTTPException(404,"Unable to load the selected Feature.")
        cursor.execute("select given_text,when_text,then_text from acceptance_criteria where feature_id=%s order by criteria_order",(feature_id,));criteria=cursor.fetchall()
    return {"feature":{"id":str(feature["id"]),"key":feature["feature_key"],"project_id":str(feature["project_id"]),"product_space_id":str(feature["product_space_id"]),"title":feature["title"],"description":feature["description"],"problem_statement":feature["problem_statement"],"business_value":feature["business_value"],"functional_requirements":feature["functional_requirements"],"non_functional_requirements":feature["non_functional_requirements"],"dependencies":feature["dependencies"],"risks":feature["risks"],"assumptions":feature["assumptions"],"priority":feature["priority"],"status":feature["status"],"acceptance_criteria":criteria,"pi_release":{"id":str(feature["release_id"]),"name":feature["pi_display_name"] or feature["pi_name"],"start_date":feature["pi_start_date"],"end_date":feature["pi_end_date"]}}}


@router.put("/features/{feature_id}/regenerated")
def save_regenerated_feature(feature_id: UUID,request: RegeneratedFeatureSave) -> dict:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("select organization_id,product_space_id,project_id,feature_key from features where id=%s and archived_at is null for update",(feature_id,));current=cursor.fetchone()
        if not current: raise HTTPException(404,"Feature not found.")
        cursor.execute("select 1 from releases where id=%s and project_id=%s and archived_at is null",(request.pi_release_id,current["project_id"]))
        if not cursor.fetchone(): raise HTTPException(422,"The selected PI Release does not belong to this Project.")
        f=request.feature
        cursor.execute("""update features set release_id=%s,title=%s,description=%s,problem_statement=%s,business_value=%s,
          functional_requirements=%s,non_functional_requirements=%s,dependencies=%s,risks=%s,assumptions=%s,
          priority=%s,status=%s,version=version+1,updated_at=now() where id=%s""",(request.pi_release_id,f.title,f.description,f.problem_statement,f.business_value,Jsonb(f.functional_requirements),Jsonb(f.non_functional_requirements),Jsonb(f.dependencies),Jsonb(f.risks),Jsonb(f.assumptions),f.priority,request.status,feature_id))
        cursor.execute("delete from acceptance_criteria where feature_id=%s",(feature_id,))
        for order,criterion in enumerate(f.acceptance_criteria,1): cursor.execute("insert into acceptance_criteria(organization_id,product_space_id,project_id,feature_id,given_text,when_text,then_text,criteria_order) values(%s,%s,%s,%s,%s,%s,%s,%s)",(current["organization_id"],current["product_space_id"],current["project_id"],feature_id,criterion.given,criterion.when,criterion.then,order))
        cursor.execute("insert into activity_logs(organization_id,product_space_id,project_id,entity_type,entity_id,action,details) values(%s,%s,%s,'FEATURE',%s,'FEATURE_REGENERATED',%s)",(current["organization_id"],current["product_space_id"],current["project_id"],feature_id,Jsonb({"status":request.status})))
        connection.commit()
    return {"success":True,"feature":{"id":str(feature_id),"key":current["feature_key"],"title":f.title},"message":f"{current['feature_key']} regenerated and saved."}


@router.post("/projects/{project_id}/work-items", status_code=201)
def create_work_item(project_id: UUID, request: WorkItemCreate) -> dict:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select * from projects where id=%s for update", (project_id,))
            project = cursor.fetchone()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found.")
            cursor.execute("select * from project_sequences where project_id=%s for update", (project_id,))
            sequence = cursor.fetchone()
            if request.item_type == "FEATURE":
                if not request.pi_release_id: raise HTTPException(422,"PI Release is required.")
                cursor.execute("select 1 from releases where id=%s and project_id=%s and archived_at is null",(request.pi_release_id,project_id))
                if not cursor.fetchone(): raise HTTPException(422,"The selected PI Release does not belong to this Project.")
                key = f'{project["project_key"]}-F-{sequence["next_feature_number"]:03d}'
                cursor.execute(
                    """insert into features(organization_id,product_space_id,project_id,release_id,feature_key,title,
                       description,status,priority,source) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'MANUAL') returning id,version""",
                    (project["organization_id"],project["product_space_id"],project_id,request.pi_release_id,key,
                     request.title,request.description,request.status,request.priority),
                )
                created=cursor.fetchone(); cursor.execute("update project_sequences set next_feature_number=next_feature_number+1 where project_id=%s",(project_id,))
            else:
                if not request.parent_feature_id:
                    raise HTTPException(status_code=422,detail="A user story requires a parent feature.")
                cursor.execute("select release_id from features where id=%s and project_id=%s and archived_at is null",(request.parent_feature_id,project_id));parent=cursor.fetchone()
                if not parent: raise HTTPException(status_code=422,detail="Parent feature is invalid or belongs to another project.")
                if request.pi_release_id and request.pi_release_id!=parent["release_id"]: raise HTTPException(422,"User Story PI must match its parent Feature PI Release.")
                story_pi=parent["release_id"]
                cursor.execute("select 1 from releases where id=%s and project_id=%s and archived_at is null",(story_pi,project_id))
                if not cursor.fetchone(): raise HTTPException(422,"The selected PI Release does not belong to this Project.")
                key=f'{project["project_key"]}-{sequence["next_story_number"]}'
                cursor.execute(
                    """insert into user_stories(organization_id,product_space_id,project_id,feature_id,release_id,story_key,
                       title,story_text,status,priority,story_points,source) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'MANUAL') returning id,version""",
                    (project["organization_id"],project["product_space_id"],project_id,request.parent_feature_id,story_pi,
                     key,request.title,request.description,request.status,request.priority,request.story_points),
                )
                created=cursor.fetchone(); cursor.execute("update project_sequences set next_story_number=next_story_number+1 where project_id=%s",(project_id,))
            cursor.execute("insert into activity_logs(organization_id,product_space_id,project_id,entity_type,entity_id,action) values (%s,%s,%s,%s,%s,'WORK_ITEM_CREATED')",(project["organization_id"],project["product_space_id"],project_id,request.item_type,created["id"]))
        connection.commit()
    return {"id":str(created["id"]),"key":key,"version":created["version"],"message":f"{key} created."}


@router.patch("/projects/{project_id}/work-items/{item_type}/{item_id}")
def update_work_item(project_id: UUID, item_type: Literal["feature", "story"], item_id: UUID, request: WorkItemUpdate) -> dict:
    table, description_column = ("features","description") if item_type=="feature" else ("user_stories","story_text")
    values=request.model_dump(exclude_none=True,exclude={"version"})
    if "description" in values: values[description_column]=values.pop("description")
    if not values: raise HTTPException(status_code=422,detail="No changes supplied.")
    allowed={"title",description_column,"status","priority","story_points"}
    values={key:value for key,value in values.items() if key in allowed}
    assignments=", ".join(f"{key}=%s" for key in values)
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"update {table} set {assignments},version=version+1,updated_at=now() where id=%s and project_id=%s and version=%s and archived_at is null returning version",(*values.values(),item_id,project_id,request.version))
        updated=cursor.fetchone()
        if not updated: raise HTTPException(status_code=409,detail="This item changed or no longer exists. Refresh and retry.")
        connection.commit()
    return {"success":True,"version":updated["version"],"message":"Changes saved."}


@router.delete("/projects/{project_id}/work-items/{item_type}/{item_id}")
def archive_work_item(project_id: UUID, item_type: Literal["feature", "story"], item_id: UUID) -> dict:
    table="features" if item_type=="feature" else "user_stories"
    with get_connection() as connection, connection.cursor() as cursor:
        child_count=0
        if item_type=="feature":
            cursor.execute("select count(*) n from user_stories where feature_id=%s and project_id=%s and archived_at is null",(item_id,project_id));child_count=cursor.fetchone()["n"]
            cursor.execute("update user_stories set archived_at=now(),updated_at=now() where feature_id=%s and project_id=%s and archived_at is null",(item_id,project_id))
        cursor.execute(f"update {table} set archived_at=now(),updated_at=now() where id=%s and project_id=%s and archived_at is null returning id",(item_id,project_id))
        if not cursor.fetchone(): raise HTTPException(status_code=404,detail="Work item not found.")
        connection.commit()
    return {"success":True,"archived_children":child_count,"message":f"Work item archived{f' with {child_count} user stories' if child_count else ''}."}


@router.delete("/projects/{project_id}/work-items/{item_type}/{item_id}/permanent")
def permanently_delete_work_item(project_id: UUID,item_type: Literal["feature","story"],item_id: UUID) -> dict:
    table="features" if item_type=="feature" else "user_stories"
    with get_connection() as connection, connection.cursor() as cursor:
        if item_type=="feature":
            cursor.execute("select count(*) n from user_stories where feature_id=%s",(item_id,));children=cursor.fetchone()["n"]
            if children: raise HTTPException(status_code=409,detail=f"This feature contains {children} user stories. Archive the hierarchy or move/delete the stories first.")
        cursor.execute(f"delete from {table} where id=%s and project_id=%s returning id",(item_id,project_id))
        if not cursor.fetchone(): raise HTTPException(status_code=404,detail="Work item not found.")
        connection.commit()
    return {"success":True,"message":"Work item permanently deleted."}


def _statuses(mode: str) -> tuple[str, str]:
    return {"DRAFT": ("DRAFT", "DRAFT"), "BACKLOG": ("PLANNED", "BACKLOG"), "SPRINT": ("PLANNED", "READY")}[mode]


@router.post("/projects/{project_id}/generated-work-items", status_code=status.HTTP_201_CREATED)
def save_generated_work_items(
    project_id: UUID,
    request: SaveGeneratedItemsRequest,
    idempotency_key: str = Header(min_length=8, max_length=200),
) -> dict:
    if project_id != request.project_id:
        raise HTTPException(status_code=400, detail="Project ID mismatch.")
    if not request.feature and not request.user_stories:
        raise HTTPException(status_code=422, detail="At least one generated work item is required.")
    if not request.release_id:
        raise HTTPException(status_code=422,detail="PI Release is required.")
    if request.user_stories and not request.feature and not request.parent_feature_id:
        raise HTTPException(status_code=422, detail="Generated user stories require a parent feature.")
    feature_status, story_status = _statuses(request.save_mode)
    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("select response from idempotency_keys where key=%s and project_id=%s", (idempotency_key, project_id))
                existing = cursor.fetchone()
                if existing and existing["response"]:
                    return existing["response"]
                cursor.execute(
                    """select p.*, ps.organization_id space_organization_id from projects p
                       join product_spaces ps on ps.id=p.product_space_id
                       where p.id=%s and p.product_space_id=%s for update""",
                    (project_id, request.product_space_id),
                )
                project = cursor.fetchone()
                if not project:
                    raise HTTPException(status_code=404, detail="Project does not belong to the selected product space.")
                cursor.execute("select 1 from releases where id=%s and project_id=%s and archived_at is null",(request.release_id,project_id))
                if not cursor.fetchone(): raise HTTPException(status_code=422,detail="The selected PI Release does not belong to this Project.")
                cursor.execute("insert into idempotency_keys(key, project_id) values (%s,%s)", (idempotency_key, project_id))
                content = request.model_dump(mode="json", exclude={"input_prompt"})
                generation_type = "FEATURE_WITH_STORIES" if request.feature and request.user_stories else ("FEATURE" if request.feature else "USER_STORIES")
                cursor.execute(
                    """insert into ai_generations(organization_id, product_space_id, project_id,
                       generation_type, input_prompt, generated_content, model_name)
                       values (%s,%s,%s,%s,%s,%s,%s) returning id""",
                    (project["organization_id"], request.product_space_id, project_id, generation_type,
                     request.input_prompt, Jsonb(content), "configured-openai-model"),
                )
                generation_id = cursor.fetchone()["id"]
                cursor.execute("select * from project_sequences where project_id=%s for update", (project_id,))
                sequence = cursor.fetchone()
                feature_id = request.parent_feature_id
                if request.user_stories and not request.feature:
                    cursor.execute("select release_id from features where id=%s and project_id=%s and archived_at is null",(feature_id,project_id));parent=cursor.fetchone()
                    if not parent: raise HTTPException(422,"Parent Feature is invalid.")
                    if parent["release_id"]!=request.release_id: raise HTTPException(422,"User Story PI must match its parent Feature PI Release.")
                feature_result = None
                if request.feature:
                    feature_key = f'{project["project_key"]}-F-{sequence["next_feature_number"]:03d}'
                    cursor.execute(
                        """insert into features(organization_id, product_space_id, project_id, feature_key,
                           title,description,problem_statement,business_value,functional_requirements,
                           non_functional_requirements,dependencies,risks,assumptions,priority,status,release_id,ai_generation_id)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                        (project["organization_id"], request.product_space_id, project_id, feature_key,
                         request.feature.title,request.feature.description,request.feature.problem_statement,
                         request.feature.business_value,Jsonb(request.feature.functional_requirements),
                         Jsonb(request.feature.non_functional_requirements),Jsonb(request.feature.dependencies),
                         Jsonb(request.feature.risks),Jsonb(request.feature.assumptions),request.feature.priority,
                         feature_status,request.release_id,generation_id),
                    )
                    feature_id = cursor.fetchone()["id"]
                    for order, criterion in enumerate(request.feature.acceptance_criteria, 1):
                        cursor.execute(
                            """insert into acceptance_criteria(organization_id, product_space_id, project_id,
                               feature_id, given_text, when_text, then_text, criteria_order)
                               values (%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (project["organization_id"], request.product_space_id, project_id, feature_id,
                             criterion.given, criterion.when, criterion.then, order),
                        )
                    sequence["next_feature_number"] += 1
                    feature_result = {"id": str(feature_id), "key": feature_key, "title": request.feature.title}
                saved_stories = []
                for story in request.user_stories:
                    story_key = f'{project["project_key"]}-{sequence["next_story_number"]}'
                    cursor.execute(
                        """insert into user_stories(organization_id, product_space_id, project_id, feature_id,
                           story_key,title,story_text,status,priority,story_points,release_id,sprint_id,ai_generation_id)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                        (project["organization_id"], request.product_space_id, project_id, feature_id,
                         story_key,story.title,story.story,story_status,story.priority,story.story_points,request.release_id,
                         request.sprint_id, generation_id),
                    )
                    story_id = cursor.fetchone()["id"]
                    for order, criterion in enumerate(story.acceptance_criteria, 1):
                        cursor.execute(
                            """insert into acceptance_criteria(organization_id, product_space_id, project_id,
                               user_story_id, given_text, when_text, then_text, criteria_order)
                               values (%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (project["organization_id"], request.product_space_id, project_id, story_id,
                             criterion.given, criterion.when, criterion.then, order),
                        )
                    saved_stories.append({"id": str(story_id), "key": story_key, "title": story.title})
                    sequence["next_story_number"] += 1
                cursor.execute(
                    """update project_sequences set next_feature_number=%s, next_story_number=%s,
                       updated_at=now() where project_id=%s""",
                    (sequence["next_feature_number"], sequence["next_story_number"], project_id),
                )
                cursor.execute("update ai_generations set status='SAVED', saved_at=now() where id=%s", (generation_id,))
                cursor.execute(
                    """insert into activity_logs(organization_id, product_space_id, project_id, entity_type,
                       entity_id, action, details) values (%s,%s,%s,%s,%s,'AI_GENERATION_SAVED',%s)""",
                    (project["organization_id"], request.product_space_id, project_id,
                     "FEATURE" if feature_id else "USER_STORY", feature_id, Jsonb({"storiesSaved": len(saved_stories)})),
                )
                result = {"success": True, "ai_generation_id": str(generation_id), "feature": feature_result,
                          "user_stories": saved_stories, "saved_stories": len(saved_stories),
                          "message": f"Saved {1 if feature_result else 0} feature and {len(saved_stories)} user stories."}
                cursor.execute("update idempotency_keys set response=%s where key=%s", (Jsonb(result), idempotency_key))
            connection.commit()
            return result
        except HTTPException:
            connection.rollback()
            raise
        except Exception as error:
            connection.rollback()
            raise HTTPException(status_code=500, detail="Unable to save generated work items.") from error
