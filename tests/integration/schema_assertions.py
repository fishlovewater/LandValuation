def table_exists(cursor, table_name: str, schema: str = "public") -> bool:
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s)",
        (schema, table_name),
    )
    return cursor.fetchone()[0]


def column_names(cursor, table_name: str, schema: str = "public") -> list[str]:
    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, table_name),
    )
    return [row[0] for row in cursor.fetchall()]


def unique_columns(cursor, table_name: str, schema: str = "public") -> set[tuple[str, ...]]:
    cursor.execute(
        """
        SELECT array_agg(attribute.attname ORDER BY ordinality)
        FROM pg_constraint pg_constraint_row
        JOIN pg_class relation ON relation.oid = pg_constraint_row.conrelid
        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        CROSS JOIN LATERAL unnest(pg_constraint_row.conkey) WITH ORDINALITY AS key(attribute_number, ordinality)
        JOIN pg_attribute attribute ON attribute.attrelid = relation.oid AND attribute.attnum = key.attribute_number
        WHERE namespace.nspname = %s AND relation.relname = %s AND pg_constraint_row.contype IN ('p', 'u')
        GROUP BY pg_constraint_row.oid
        """,
        (schema, table_name),
    )
    return {tuple(row[0]) for row in cursor.fetchall()}


def numeric_precision_scale(cursor, table_name: str, column_name: str, schema: str = "public") -> tuple[int | None, int | None]:
    cursor.execute(
        "SELECT numeric_precision, numeric_scale FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name = %s",
        (schema, table_name, column_name),
    )
    return tuple(cursor.fetchone())


def check_accepts(cursor, table_name: str, values: dict[str, object], schema: str = "public") -> bool:
    columns = ", ".join(f'"{column}"' for column in values)
    placeholders = ", ".join(["%s"] * len(values))
    cursor.execute("SAVEPOINT schema_assertion")
    try:
        cursor.execute(f'INSERT INTO "{schema}"."{table_name}" ({columns}) VALUES ({placeholders})', tuple(values.values()))
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT schema_assertion")
        return False
    cursor.execute("ROLLBACK TO SAVEPOINT schema_assertion")
    return True
