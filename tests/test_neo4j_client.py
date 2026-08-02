from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from neo4j import RoutingControl

from app.neo4j_client import Neo4jClient


class Neo4jClientTests(unittest.TestCase):
    @patch("app.neo4j_client.GraphDatabase.driver")
    def test_reuses_driver_and_parameterizes_reads(self, create_driver) -> None:
        record = MagicMock()
        record.data.return_value = {"value": 1}
        driver = create_driver.return_value
        driver.execute_query.return_value = ([record], MagicMock(), ["value"])

        client = Neo4jClient()
        client.verify_connectivity()
        result = client.execute_read("RETURN $value AS value", {"value": 1})
        client.close()

        self.assertEqual([{"value": 1}], result)
        driver.verify_connectivity.assert_called_once_with()
        driver.execute_query.assert_called_once_with(
            "RETURN $value AS value",
            parameters_={"value": 1},
            database_="neo4j",
            routing_=RoutingControl.READ,
        )
        driver.close.assert_called_once_with()

    @patch("app.neo4j_client.GraphDatabase.driver")
    def test_parameterizes_writes(self, create_driver) -> None:
        create_driver.return_value.execute_query.return_value = ([], MagicMock(), [])
        client = Neo4jClient()

        result = client.execute_write(
            "MERGE (n:Example {id: $id})", {"id": "stable-id"}
        )

        self.assertEqual([], result)
        create_driver.return_value.execute_query.assert_called_once_with(
            "MERGE (n:Example {id: $id})",
            parameters_={"id": "stable-id"},
            database_="neo4j",
            routing_=RoutingControl.WRITE,
        )


if __name__ == "__main__":
    unittest.main()
