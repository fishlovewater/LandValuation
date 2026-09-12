def _snapshot_table_exists(cursor) -> bool:
    cursor.execute(
        """
        SELECT to_regclass('review.external_input_snapshots') IS NOT NULL
        """
    )
    return bool(cursor.fetchone()[0])


def _run_snapshot_column_exists(cursor) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'valuation'
              AND table_name = 'validation_runs'
              AND column_name = 'external_input_snapshot_id'
        )
        """
    )
    return bool(cursor.fetchone()[0])


def test_external_review_input_snapshot_schema_and_runtime_immutability(
    admin_cursor, db_cursor
):
    assert _snapshot_table_exists(admin_cursor)
    assert _run_snapshot_column_exists(admin_cursor)

    admin_cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS relation
              ON relation.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'valuation'
              AND relation.relname = 'validation_runs'
              AND constraint_row.conname = 'fk_validation_runs_external_input_snapshot'
        )
        """
    )
    assert admin_cursor.fetchone() == (True,)

    db_cursor.execute(
        """
        SELECT
            has_table_privilege(current_user, 'review.external_input_snapshots', 'SELECT'),
            has_table_privilege(current_user, 'review.external_input_snapshots', 'INSERT'),
            has_table_privilege(current_user, 'review.external_input_snapshots', 'UPDATE'),
            has_table_privilege(current_user, 'review.external_input_snapshots', 'DELETE')
        """
    )
    assert db_cursor.fetchone() == (True, True, False, False)


def test_external_review_input_snapshot_migration_roundtrips(
    admin_cursor, migration_roundtrip
):
    assert _snapshot_table_exists(admin_cursor)
    assert _run_snapshot_column_exists(admin_cursor)
    # End the catalog-reading transaction before Alembic mutates those same
    # relations from its separate connection.  This also guarantees the next
    # assertions observe a fresh PostgreSQL catalog snapshot.
    admin_cursor.connection.commit()

    migration_roundtrip('downgrade', '20260912_0023')
    assert not _snapshot_table_exists(admin_cursor)
    assert not _run_snapshot_column_exists(admin_cursor)
    admin_cursor.connection.commit()

    migration_roundtrip('upgrade', 'head')
    assert _snapshot_table_exists(admin_cursor)
    assert _run_snapshot_column_exists(admin_cursor)
