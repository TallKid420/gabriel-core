-- Enable the pgvector extension in the gabriel_core database on first init.
-- The Alembic migration also runs CREATE EXTENSION IF NOT EXISTS vector, so this is a
-- belt-and-suspenders step that guarantees the extension is present even before
-- migrations run.
CREATE EXTENSION IF NOT EXISTS vector;
