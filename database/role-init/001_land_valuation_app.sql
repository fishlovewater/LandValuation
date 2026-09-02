\set ON_ERROR_STOP on

SELECT format('CREATE ROLE %I NOLOGIN', :'app_group_role')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'app_group_role'
)
\gexec

SELECT format('GRANT %I TO %I', :'app_group_role', :'app_login_role')
WHERE NOT pg_has_role(:'app_login_role', :'app_group_role', 'member')
\gexec
