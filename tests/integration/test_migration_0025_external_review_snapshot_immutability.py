def _snapshot_trigger_exists(cursor) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_trigger AS trigger_row
            JOIN pg_class AS relation
              ON relation.oid = trigger_row.tgrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'review'
              AND relation.relname = 'external_input_snapshots'
              AND trigger_row.tgname = 'trg_external_input_snapshots_immutable'
              AND NOT trigger_row.tgisinternal
        )
        """
    )
    return bool(cursor.fetchone()[0])


def test_external_review_input_snapshot_has_database_immutability_trigger(admin_cursor):
    assert _snapshot_trigger_exists(admin_cursor)


def test_external_review_snapshot_immutability_migration_roundtrips(
    admin_cursor, migration_roundtrip
):
    assert _snapshot_trigger_exists(admin_cursor)
    admin_cursor.connection.commit()

    migration_roundtrip('downgrade', '20260912_0024')
    assert not _snapshot_trigger_exists(admin_cursor)
    admin_cursor.connection.commit()

    migration_roundtrip('upgrade', 'head')
    assert _snapshot_trigger_exists(admin_cursor)
