\set ON_ERROR_STOP on

SELECT format('CREATE ROLE %I NOLOGIN', :'app_group_role')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'app_group_role'
)
\gexec

SELECT format('GRANT %I TO %I', :'app_group_role', :'app_login_role')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_auth_members AS membership
    JOIN pg_roles AS group_role ON group_role.oid = membership.roleid
    JOIN pg_roles AS login_role ON login_role.oid = membership.member
    WHERE group_role.rolname = :'app_group_role'
      AND login_role.rolname = :'app_login_role'
)
\gexec
