from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "infra" / "neo4j" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from neo4j_migrate import discover_migrations, parse_cypher_statements  # noqa: E402


class CypherParserTests(unittest.TestCase):
    def test_handles_comments_and_semicolons_in_strings(self) -> None:
        content = """
        // comment with ;
        CREATE (n:Example {single: 'a;b', double: "c;d"});
        /* block ; comment */
        MATCH (n:`Odd;Label`) RETURN n;
        """
        statements = parse_cypher_statements(content)
        self.assertEqual(2, len(statements))
        self.assertIn("'a;b'", statements[0])
        self.assertIn("`Odd;Label`", statements[1])

    def test_handles_escaped_and_doubled_quotes(self) -> None:
        content = r"RETURN 'it\'s;ok' AS first; RETURN 'it''s;also' AS second;"
        statements = parse_cypher_statements(content)
        self.assertEqual(2, len(statements))

    def test_rejects_unterminated_input(self) -> None:
        with self.assertRaises(ValueError):
            parse_cypher_statements("RETURN 'unfinished;")

    def test_discovers_versioned_migrations(self) -> None:
        migrations = discover_migrations(SCRIPTS.parent / "migrations")
        self.assertEqual(list(range(1, 9)), [item.number for item in migrations])
        self.assertTrue(all(len(item.checksum) == 64 for item in migrations))


if __name__ == "__main__":
    unittest.main()
