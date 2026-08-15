import logging
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import HTTPException

logger = logging.getLogger(__name__)


@dataclass
class DeletionReport:
    entity_type: str
    entity_id: UUID
    deleted_counts: dict[str, int] = field(default_factory=dict)
    unassigned_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        result = {"deleted": True, "entity_type": self.entity_type, "entity_id": str(self.entity_id),
                  "deleted_counts": self.deleted_counts}
        if self.unassigned_counts:
            result["unassigned_counts"] = self.unassigned_counts
        return result


class CascadeDeleteService:
    """Dependency-aware hard deletes. The caller owns the transaction."""

    def __init__(self, cursor, actor: str = "local-user"):
        self.cursor = cursor
        self.actor = actor

    def _one(self, table: str, entity_id: UUID):
        self.cursor.execute(f"select * from {table} where id=%s for update", (entity_id,))
        row = self.cursor.fetchone()
        if not row:
            raise HTTPException(404, f"{table.replace('_', ' ').title()} not found.")
        self._authorize(table, row)
        return row

    def _authorize(self, table: str, row: dict) -> None:
        """Enforce membership when the authentication adapter supplies a UUID actor.

        The bundled local UI uses ``local-user`` until JWT middleware is installed.
        """
        try:
            actor_id = UUID(self.actor)
        except (ValueError, TypeError):
            return
        if table == "organizations":
            if not self._table_exists("organization_members"):
                raise HTTPException(403, "Organization authorization is not configured.")
            self.cursor.execute("select 1 from organization_members where organization_id=%s and user_id=%s and role in ('ORGANIZATION_ADMIN','ADMIN')", (row["id"], actor_id))
        elif table == "product_spaces":
            if not self._table_exists("product_space_members"):
                raise HTTPException(403, "Product Space authorization is not configured.")
            self.cursor.execute("""select 1 from product_space_members where product_space_id=%s and user_id=%s and role in ('PRODUCT_SPACE_ADMIN','ADMIN')
              union all select 1 from organization_members where organization_id=%s and user_id=%s and role in ('ORGANIZATION_ADMIN','ADMIN') limit 1""", (row["id"], actor_id, row["organization_id"], actor_id))
        else:
            project_id = row["id"] if table == "projects" else row.get("project_id")
            if not project_id or not self._table_exists("project_members"):
                raise HTTPException(403, "Project authorization is not configured.")
            self.cursor.execute("""select 1 from project_members where project_id=%s and user_id=%s and role in ('PROJECT_ADMIN','PRODUCT_OWNER','SCRUM_MASTER','DEVELOPER','QA_ENGINEER','ADMIN')
              union all select 1 from projects p join product_space_members m on m.product_space_id=p.product_space_id where p.id=%s and m.user_id=%s and m.role in ('PRODUCT_SPACE_ADMIN','ADMIN')
              union all select 1 from projects p join organization_members m on m.organization_id=p.organization_id where p.id=%s and m.user_id=%s and m.role in ('ORGANIZATION_ADMIN','ADMIN') limit 1""", (project_id, actor_id, project_id, actor_id, project_id, actor_id))
        if not self.cursor.fetchone():
            raise HTTPException(403, "You do not have permission to permanently delete this entity.")

    def _count(self, table: str, clause: str, args: tuple) -> int:
        self.cursor.execute(f"select count(*) n from {table} where {clause}", args)
        return self.cursor.fetchone()["n"]

    def _delete(self, table: str, clause: str, args: tuple) -> int:
        self.cursor.execute(f"delete from {table} where {clause}", args)
        return self.cursor.rowcount

    def _log(self, report: DeletionReport):
        logger.info("hard_delete actor=%s entity_type=%s entity_id=%s counts=%s",
                    self.actor, report.entity_type, report.entity_id, report.deleted_counts)

    def delete_user_story(self, story_id: UUID) -> dict:
        story = self._one("user_stories", story_id)
        counts = {"acceptance_criteria": self._delete("acceptance_criteria", "user_story_id=%s", (story_id,)),
                  "activity_logs": self._delete("activity_logs", "entity_type='USER_STORY' and entity_id=%s", (story_id,))}
        counts["user_stories"] = self._delete("user_stories", "id=%s and project_id=%s", (story_id, story["project_id"]))
        self._delete_unreferenced_generations(story["project_id"])
        report = DeletionReport("USER_STORY", story_id, counts); self._log(report)
        return report.as_dict()

    def feature_dependencies(self, feature_id: UUID) -> dict:
        self._one("features", feature_id)
        return {
            "user_stories": self._count("user_stories", "feature_id=%s", (feature_id,)),
            "acceptance_criteria": self._count("acceptance_criteria", "feature_id=%s or user_story_id in (select id from user_stories where feature_id=%s)", (feature_id, feature_id)),
        }

    def delete_feature(self, feature_id: UUID, cascade: bool) -> dict:
        feature = self._one("features", feature_id)
        deps = {"user_stories": self._count("user_stories", "feature_id=%s", (feature_id,)),
                "acceptance_criteria": self._count("acceptance_criteria", "feature_id=%s or user_story_id in (select id from user_stories where feature_id=%s)", (feature_id, feature_id))}
        if any(deps.values()) and not cascade:
            raise HTTPException(409, {"code": "FEATURE_HAS_DEPENDENCIES", "message": "This Feature has dependent records.", "dependencies": deps})
        counts = {"acceptance_criteria": self._delete("acceptance_criteria", "feature_id=%s or user_story_id in (select id from user_stories where feature_id=%s)", (feature_id, feature_id)),
                  "activity_logs": self._delete("activity_logs", "(entity_type='FEATURE' and entity_id=%s) or (entity_type='USER_STORY' and entity_id in (select id from user_stories where feature_id=%s))", (feature_id, feature_id)),
                  "user_stories": self._delete("user_stories", "feature_id=%s", (feature_id,))}
        counts["features"] = self._delete("features", "id=%s", (feature_id,))
        counts["ai_generations"] = self._delete_unreferenced_generations(feature["project_id"])
        report = DeletionReport("FEATURE", feature_id, counts); self._log(report)
        return report.as_dict()

    def delete_sprint(self, sprint_id: UUID) -> dict:
        sprint = self._one("sprints", sprint_id)
        self.cursor.execute("update user_stories set sprint_id=null,updated_at=now() where sprint_id=%s", (sprint_id,))
        unassigned = self.cursor.rowcount
        counts = {"sprints": self._delete("sprints", "id=%s and project_id=%s", (sprint_id, sprint["project_id"]))}
        report = DeletionReport("SPRINT", sprint_id, counts, {"user_stories": unassigned}); self._log(report)
        return report.as_dict()

    def delete_release(self, release_id: UUID, cascade: bool) -> dict:
        release = self._one("releases", release_id)
        deps = {t: self._count(t, "release_id=%s", (release_id,)) for t in ("sprints", "features", "user_stories")}
        if any(deps.values()) and not cascade:
            raise HTTPException(409, {"code": "RELEASE_HAS_DEPENDENCIES", "message": "This Release has dependent records.", "dependencies": deps})
        counts = {
            "acceptance_criteria": self._delete("acceptance_criteria", "feature_id in (select id from features where release_id=%s) or user_story_id in (select id from user_stories where release_id=%s)", (release_id, release_id)),
            "activity_logs": self._delete("activity_logs", "project_id=%s and entity_id in (select id from features where release_id=%s union select id from user_stories where release_id=%s)", (release["project_id"], release_id, release_id)),
            "user_stories": self._delete("user_stories", "release_id=%s", (release_id,)),
            "features": self._delete("features", "release_id=%s", (release_id,)),
            "sprints": self._delete("sprints", "release_id=%s", (release_id,)),
        }
        counts["releases"] = self._delete("releases", "id=%s", (release_id,))
        counts["ai_generations"] = self._delete_unreferenced_generations(release["project_id"])
        report = DeletionReport("RELEASE", release_id, counts); self._log(report)
        return report.as_dict()

    def project_dependencies(self, project_id: UUID) -> dict:
        self._one("projects", project_id)
        dependencies = {t: self._count(t, "project_id=%s", (project_id,)) for t in ("releases", "sprints", "features", "user_stories", "acceptance_criteria")}
        if self._table_exists("chat_sessions"):
            dependencies["chat_sessions"] = self._count("chat_sessions", "project_id=%s", (project_id,))
        return dependencies

    def delete_project(self, project_id: UUID, cascade: bool) -> dict:
        self._one("projects", project_id)
        deps = self.project_dependencies(project_id)
        if any(deps.values()) and not cascade:
            raise HTTPException(409, {"code": "PROJECT_HAS_DEPENDENCIES", "message": "This Project has dependent records.", "dependencies": deps})
        counts = {}
        if self._table_exists("chat_sessions"):
            for table in ("chat_runs", "chat_retrieval_events", "chat_message_intents", "chat_messages"):
                counts[table] = self._delete(table, "session_id in (select id from chat_sessions where project_id=%s)", (project_id,))
            counts["chat_sessions"] = self._delete("chat_sessions", "project_id=%s", (project_id,))
        for table in ("acceptance_criteria", "user_stories", "features", "sprints", "releases", "ai_generations", "project_sequences", "idempotency_keys", "activity_logs"):
            counts[table] = self._delete(table, "project_id=%s", (project_id,))
        if self._table_exists("project_members"):
            counts["project_members"] = self._delete("project_members", "project_id=%s", (project_id,))
        counts["projects"] = self._delete("projects", "id=%s", (project_id,))
        report = DeletionReport("PROJECT", project_id, counts); self._log(report)
        return report.as_dict()

    def delete_product_space(self, space_id: UUID, cascade: bool) -> dict:
        self._one("product_spaces", space_id)
        self.cursor.execute("select id from projects where product_space_id=%s order by id for update", (space_id,))
        project_ids = [r["id"] for r in self.cursor.fetchall()]
        if project_ids and not cascade:
            raise HTTPException(409, {"code": "PRODUCT_SPACE_HAS_DEPENDENCIES", "message": "This Product Space contains Projects.", "dependencies": {"projects": len(project_ids)}})
        total = {}
        for project_id in project_ids:
            child = self.delete_project(project_id, True)["deleted_counts"]
            for key, value in child.items(): total[key] = total.get(key, 0) + value
        if self._table_exists("product_space_members"):
            total["product_space_members"] = self._delete("product_space_members", "product_space_id=%s", (space_id,))
        total["product_spaces"] = self._delete("product_spaces", "id=%s", (space_id,))
        report = DeletionReport("PRODUCT_SPACE", space_id, total); self._log(report)
        return report.as_dict()

    def delete_organization(self, organization_id: UUID, cascade: bool) -> dict:
        self._one("organizations", organization_id)
        self.cursor.execute("select id from product_spaces where organization_id=%s order by id for update", (organization_id,))
        space_ids = [r["id"] for r in self.cursor.fetchall()]
        if space_ids and not cascade:
            raise HTTPException(409, {"code": "ORGANIZATION_HAS_DEPENDENCIES", "message": "This Organization contains Product Spaces.", "dependencies": {"product_spaces": len(space_ids)}})
        total = {}
        for space_id in space_ids:
            child = self.delete_product_space(space_id, True)["deleted_counts"]
            for key, value in child.items(): total[key] = total.get(key, 0) + value
        if self._table_exists("organization_members"):
            total["organization_members"] = self._delete("organization_members", "organization_id=%s", (organization_id,))
        total["organizations"] = self._delete("organizations", "id=%s", (organization_id,))
        report = DeletionReport("ORGANIZATION", organization_id, total); self._log(report)
        return report.as_dict()

    def reset_application_data(self) -> dict[str, int]:
        impact_order = [
            'generated_change_validations', 'generated_changes',
            'analysis_score_history', 'impact_findings', 'impact_evidence',
            'impact_requirements', 'impact_analysis_runs',
            'repository_source_chunks', 'repository_source_edges',
            'repository_source_symbols', 'repository_source_files',
            'repository_snapshots',
        ]
        order = ["chat_runs", "chat_retrieval_events", "chat_message_intents", "chat_messages", "chat_sessions",
                 "acceptance_criteria", "user_stories", "features", "sprints", "releases", "ai_generations",
                 "project_sequences", "idempotency_keys", "activity_logs", "project_members", "product_space_members",
                 "organization_members", "projects", "product_spaces", "organizations", "document_chunks",
                 "documents", "connection_test", "escalated_table"]
        counts = {}
        for table in impact_order + order:
            if self._table_exists(table): counts[table] = self._delete(table, "true", ())
        logger.warning("application_data_reset actor=%s counts=%s", self.actor, counts)
        return counts

    def _delete_unreferenced_generations(self, project_id: UUID) -> int:
        return self._delete("ai_generations", "project_id=%s and not exists(select 1 from features f where f.ai_generation_id=ai_generations.id) and not exists(select 1 from user_stories u where u.ai_generation_id=ai_generations.id)", (project_id,))

    def _table_exists(self, table: str) -> bool:
        self.cursor.execute("select to_regclass(%s) is not null present", (f"public.{table}",))
        return self.cursor.fetchone()["present"]
