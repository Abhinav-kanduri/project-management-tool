import unittest

from fastapi import HTTPException

from app.database import get_connection
from app.services.deletion import CascadeDeleteService


class DeletionServiceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.context = get_connection()
        self.connection = self.context.__enter__()
        self.cursor = self.connection.cursor()
        c = self.cursor
        c.execute("insert into organizations(name) values('Deletion test') returning id"); self.org = c.fetchone()["id"]
        c.execute("insert into product_spaces(organization_id,name,space_key) values(%s,'Deletion test','DELTEST') returning id", (self.org,)); self.space = c.fetchone()["id"]
        c.execute("insert into projects(organization_id,product_space_id,project_key,name) values(%s,%s,'DELTEST','Deletion test') returning id", (self.org, self.space)); self.project = c.fetchone()["id"]
        c.execute("insert into project_sequences(project_id) values(%s)", (self.project,))
        c.execute("insert into releases(organization_id,product_space_id,project_id,name,display_name,year,pi_number) values(%s,%s,%s,'Test PI','Test PI',2099,1) returning id", (self.org, self.space, self.project)); self.release = c.fetchone()["id"]

    def tearDown(self):
        self.connection.rollback()
        self.cursor.close()
        self.context.__exit__(None, None, None)

    def feature(self, with_story=True, with_criterion=True):
        c = self.cursor
        c.execute("insert into features(organization_id,product_space_id,project_id,release_id,feature_key,title) values(%s,%s,%s,%s,'DEL-F-001','Delete feature') returning id", (self.org, self.space, self.project, self.release)); feature = c.fetchone()["id"]
        story = None
        if with_story:
            c.execute("insert into user_stories(organization_id,product_space_id,project_id,feature_id,release_id,story_key,title) values(%s,%s,%s,%s,%s,'DEL-101','Delete story') returning id", (self.org, self.space, self.project, feature, self.release)); story = c.fetchone()["id"]
            if with_criterion:
                c.execute("insert into acceptance_criteria(organization_id,product_space_id,project_id,user_story_id) values(%s,%s,%s,%s)", (self.org, self.space, self.project, story))
        return feature, story

    def test_rejects_feature_dependencies_without_cascade(self):
        feature, _ = self.feature()
        with self.assertRaises(HTTPException) as error:
            CascadeDeleteService(self.cursor).delete_feature(feature, False)
        self.assertEqual(error.exception.status_code, 409)

    def test_cascade_deletes_feature_story_and_criterion(self):
        feature, _ = self.feature()
        report = CascadeDeleteService(self.cursor).delete_feature(feature, True)
        self.assertEqual(report["deleted_counts"]["features"], 1)
        self.assertEqual(report["deleted_counts"]["user_stories"], 1)
        self.assertEqual(report["deleted_counts"]["acceptance_criteria"], 1)

    def test_user_story_delete_without_criteria(self):
        _, story = self.feature(with_criterion=False)
        report = CascadeDeleteService(self.cursor).delete_user_story(story)
        self.assertEqual(report["deleted_counts"]["user_stories"], 1)
        self.assertEqual(report["deleted_counts"]["acceptance_criteria"], 0)

    def test_sprint_delete_unassigns_story(self):
        feature, story = self.feature()
        self.cursor.execute("insert into sprints(organization_id,product_space_id,project_id,release_id,name) values(%s,%s,%s,%s,'Test sprint') returning id", (self.org, self.space, self.project, self.release)); sprint = self.cursor.fetchone()["id"]
        self.cursor.execute("update user_stories set sprint_id=%s where id=%s", (sprint, story))
        report = CascadeDeleteService(self.cursor).delete_sprint(sprint)
        self.assertEqual(report["unassigned_counts"]["user_stories"], 1)
        self.cursor.execute("select sprint_id from user_stories where id=%s", (story,))
        self.assertIsNone(self.cursor.fetchone()["sprint_id"])


if __name__ == "__main__":
    unittest.main()
