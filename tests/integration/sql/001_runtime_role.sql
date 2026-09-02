\getenv database_name POSTGRES_DB
\getenv app_postgres_user APP_POSTGRES_USER
\getenv app_postgres_password APP_POSTGRES_PASSWORD

-- The Docker bootstrap role is superuser. Provision extensions and create the
-- non-superuser migration database owner before tests run.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'land_valuation_migrator') THEN
        CREATE ROLE land_valuation_migrator LOGIN PASSWORD 'integration-migration-owner'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END
$$;

ALTER DATABASE :"database_name" OWNER TO land_valuation_migrator;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'land_valuation_app') THEN
        CREATE ROLE land_valuation_app NOLOGIN;
    END IF;
END
$$;

REVOKE land_valuation_app FROM land_valuation_migrator;

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L IN ROLE land_valuation_app',
    :'app_postgres_user',
    :'app_postgres_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_postgres_user')
\gexec

GRANT land_valuation_app TO :"app_postgres_user";
GRANT USAGE ON SCHEMA public TO land_valuation_app;
ALTER DEFAULT PRIVILEGES FOR ROLE land_valuation_migrator
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO land_valuation_app;
ALTER DEFAULT PRIVILEGES FOR ROLE land_valuation_migrator
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO land_valuation_app;
