\getenv app_postgres_user APP_POSTGRES_USER
\getenv app_postgres_password APP_POSTGRES_PASSWORD

-- Provision extensions while Docker's bootstrap POSTGRES_USER is superuser;
-- the migration owner is deliberately demoted at the end of this script.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'land_valuation_app') THEN
        CREATE ROLE land_valuation_app NOLOGIN;
    END IF;
END
$$;

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L IN ROLE land_valuation_app',
    :'app_postgres_user',
    :'app_postgres_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_postgres_user')
\gexec

GRANT land_valuation_app TO :"app_postgres_user";
GRANT USAGE ON SCHEMA public TO land_valuation_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO land_valuation_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO land_valuation_app;

-- Docker's POSTGRES_USER starts as a superuser. The integration migration
-- owner must instead exercise the non-member path used for migration cleanup.
ALTER ROLE land_valuation_migrator NOSUPERUSER;
