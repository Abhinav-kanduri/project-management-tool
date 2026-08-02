CREATE CONSTRAINT graph_migration_version IF NOT EXISTS
FOR (migration:GraphMigration)
REQUIRE migration.version IS UNIQUE;
