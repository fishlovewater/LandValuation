from uuid import uuid4

import pytest


def _insert_case(cursor):
    case_id = uuid4()
    cursor.execute(
        """
        INSERT INTO valuation.cases (
            case_id, case_no, case_title, case_type, valuation_base_date,
            city_code, district_code, case_status
        ) VALUES (%s, %s, 'Review uniqueness migration test', 'LAND', CURRENT_DATE,
                  'NEW_TAIPEI', 'BANQIAO', 'PROCESSING')
        """,
        (case_id, f"MIG-0014-{case_id.hex}"),
    )
    return case_id


def _insert_review(cursor, case_id):
    review_id = uuid4()
    cursor.execute(
        """
        INSERT INTO review.reviews (review_id, case_id, review_type, review_status)
        VALUES (%s, %s, 'SMART_REVIEW', 'REVIEW_REQUIRED')
        """,
        (review_id, case_id),
    )
    return review_id


def _delete_case_reviews(cursor, case_id):
    cursor.execute("DELETE FROM review.reviews WHERE case_id = %s", (case_id,))
    cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (case_id,))


def _has_case_unique_constraint(cursor) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS relation
              ON relation.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'review'
              AND relation.relname = 'reviews'
              AND constraint_row.conname = 'uq_reviews_case_id'
        )
        """
    )
    return bool(cursor.fetchone()[0])


def test_upgrade_rejects_duplicate_review_case_ids_without_data_loss(
    admin_cursor, migration_roundtrip
):
    migration_roundtrip("downgrade", "20260903_0013")
    case_id = _insert_case(admin_cursor)
    _insert_review(admin_cursor, case_id)
    _insert_review(admin_cursor, case_id)
    admin_cursor.connection.commit()

    result = migration_roundtrip("upgrade", "head", expect_success=False)

    assert "cannot enforce one review per case" in (
        result.stdout + result.stderr
    ).lower()
    admin_cursor.execute(
        "SELECT count(*) FROM review.reviews WHERE case_id = %s", (case_id,)
    )
    assert admin_cursor.fetchone() == (2,)

    _delete_case_reviews(admin_cursor, case_id)
    admin_cursor.connection.commit()
    migration_roundtrip("upgrade", "head")


def test_unique_review_case_constraint_blocks_a_second_review(admin_cursor):
    case_id = _insert_case(admin_cursor)
    _insert_review(admin_cursor, case_id)

    admin_cursor.execute("SAVEPOINT duplicate_review")
    try:
        with pytest.raises(Exception) as raised:
            _insert_review(admin_cursor, case_id)
        assert "uq_reviews_case_id" in str(raised.value)
    finally:
        admin_cursor.execute("ROLLBACK TO SAVEPOINT duplicate_review")
        admin_cursor.execute("RELEASE SAVEPOINT duplicate_review")

    admin_cursor.execute(
        "SELECT count(*) FROM review.reviews WHERE case_id = %s", (case_id,)
    )
    assert admin_cursor.fetchone() == (1,)
    _delete_case_reviews(admin_cursor, case_id)
    admin_cursor.connection.commit()


def test_unique_review_case_migration_roundtrips(
    admin_cursor, migration_roundtrip
):
    assert _has_case_unique_constraint(admin_cursor)

    migration_roundtrip("downgrade", "20260903_0013")
    assert not _has_case_unique_constraint(admin_cursor)

    migration_roundtrip("upgrade", "head")
    assert _has_case_unique_constraint(admin_cursor)
