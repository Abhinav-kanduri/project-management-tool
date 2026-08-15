from uuid import UUID

import pytest

from scripts.provision_project_member import provision_project_member


PROJECT_ID = UUID("abdbbe0d-cadf-456b-ae24-8e7e549036e7")
USER_ID = UUID("9513d1fd-7b10-4cd2-88bb-aa011ccf1b53")


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))

    def fetchone(self):
        return self.rows.pop(0)


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)

    def cursor(self):
        return self.cursor_instance


def test_provisioning_requires_existing_auth_user_and_upserts_membership() -> None:
    connection = FakeConnection(
        [
            {"id": USER_ID, "email": "member@example.com"},
            {"id": PROJECT_ID, "name": "Customer Support AI Bot"},
        ]
    )

    result = provision_project_member(
        connection,
        project_id=PROJECT_ID,
        user_id=USER_ID,
        role="project_admin",
    )

    assert result == {
        "provisioned": True,
        "project_id": str(PROJECT_ID),
        "project_name": "Customer Support AI Bot",
        "user_id": str(USER_ID),
        "user_email": "member@example.com",
        "role": "PROJECT_ADMIN",
    }
    assert "on conflict (project_id, user_id)" in connection.cursor_instance.statements[-1][0]


def test_provisioning_refuses_user_missing_from_auth_users() -> None:
    connection = FakeConnection([None])

    with pytest.raises(ValueError, match="does not exist in auth.users"):
        provision_project_member(
            connection,
            project_id=PROJECT_ID,
            user_id=USER_ID,
            role="VIEWER",
        )

    assert len(connection.cursor_instance.statements) == 1


def test_check_only_validates_without_inserting() -> None:
    connection = FakeConnection(
        [
            {"id": USER_ID, "email": None},
            {"id": PROJECT_ID, "name": "Customer Support AI Bot"},
        ]
    )

    result = provision_project_member(
        connection,
        project_id=PROJECT_ID,
        user_id=USER_ID,
        role="DEVELOPER",
        check_only=True,
    )

    assert result["provisioned"] is False
    assert len(connection.cursor_instance.statements) == 2
