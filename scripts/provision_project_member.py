"""Provision an existing Supabase Auth user into a ReleaseLens Project."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


PROJECT_ROLES = (
    "PROJECT_ADMIN",
    "PRODUCT_OWNER",
    "SCRUM_MASTER",
    "DEVELOPER",
    "QA_ENGINEER",
    "VIEWER",
    "ADMIN",
)


def provision_project_member(
    connection,
    *,
    project_id: UUID,
    user_id: UUID,
    role: str,
    check_only: bool = False,
) -> dict[str, str | bool]:
    normalized_role = role.strip().upper()
    if normalized_role not in PROJECT_ROLES:
        raise ValueError(
            f"Unsupported Project role {role!r}. "
            f"Choose one of: {', '.join(PROJECT_ROLES)}"
        )

    with connection.cursor() as cursor:
        cursor.execute(
            "select id, email from auth.users where id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
        if not user:
            raise ValueError(
                f"User {user_id} does not exist in auth.users. "
                "Sign the user up through the configured identity provider first."
            )

        cursor.execute(
            "select id, name from public.projects where id = %s",
            (project_id,),
        )
        project = cursor.fetchone()
        if not project:
            raise ValueError(f"Project {project_id} does not exist.")

        if not check_only:
            cursor.execute(
                """
                insert into public.project_members (project_id, user_id, role)
                values (%s, %s, %s)
                on conflict (project_id, user_id)
                do update set role = excluded.role
                """,
                (project_id, user_id, normalized_role),
            )

    return {
        "provisioned": not check_only,
        "project_id": str(project_id),
        "project_name": str(project["name"]),
        "user_id": str(user_id),
        "user_email": str(user.get("email") or ""),
        "role": normalized_role,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add an existing auth.users identity to project_members. "
            "This command never creates an Auth user or generates a UUID."
        )
    )
    parser.add_argument("--project-id", type=UUID, required=True)
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--role", choices=PROJECT_ROLES, required=True)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate the Auth user, Project, and role without writing.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")

    args = parse_args()
    with psycopg.connect(
        database_url,
        connect_timeout=10,
        row_factory=dict_row,
    ) as connection:
        result = provision_project_member(
            connection,
            project_id=args.project_id,
            user_id=args.user_id,
            role=args.role,
            check_only=args.check_only,
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
