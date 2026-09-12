"""Distinguish automatic external-review transcription from human confirmation."""
from alembic import op

revision = "20260913_0027"
down_revision = "20260912_0026"
branch_labels = None
depends_on = None


def constraints(auto: bool):
    statuses = "'EXTRACTED', 'NEEDS_CONFIRMATION', 'CONFIRMED', 'REJECTED', 'APPLIED'"
    if auto:
        statuses += ", 'AUTO_APPLIED'"
    op.create_check_constraint("ck_extracted_fields_status", "extracted_fields",
                               f"field_status IN ({statuses})", schema="valuation")
    condition = """
        (field_status IN ('EXTRACTED', 'NEEDS_CONFIRMATION')
            AND confirmed_value IS NULL AND confirmed_by_user_id IS NULL
            AND confirmed_at IS NULL AND applied_form_instance_id IS NULL AND applied_at IS NULL)
        OR (field_status = 'REJECTED'
            AND confirmed_value IS NULL AND confirmed_by_user_id IS NOT NULL
            AND confirmed_at IS NOT NULL AND applied_form_instance_id IS NULL AND applied_at IS NULL)
        OR (field_status = 'CONFIRMED'
            AND confirmed_value IS NOT NULL AND confirmed_by_user_id IS NOT NULL
            AND confirmed_at IS NOT NULL AND applied_form_instance_id IS NULL AND applied_at IS NULL)
        OR (field_status = 'APPLIED'
            AND confirmed_value IS NOT NULL AND confirmed_by_user_id IS NOT NULL
            AND confirmed_at IS NOT NULL AND applied_form_instance_id IS NOT NULL AND applied_at IS NOT NULL)
    """
    if auto:
        condition += """
        OR (field_status = 'AUTO_APPLIED'
            AND confirmed_value IS NOT NULL AND confirmed_by_user_id IS NULL
            AND confirmed_at IS NULL AND applied_form_instance_id IS NOT NULL AND applied_at IS NOT NULL)
        """
    op.create_check_constraint("ck_extracted_fields_confirmation", "extracted_fields", condition, schema="valuation")


def upgrade():
    op.drop_constraint("ck_extracted_fields_confirmation", "extracted_fields", schema="valuation")
    op.drop_constraint("ck_extracted_fields_status", "extracted_fields", schema="valuation")
    constraints(True)


def downgrade():
    # Do not erase applied values or invent a human confirmer to roll back.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM valuation.extracted_fields WHERE field_status = 'AUTO_APPLIED') THEN
            RAISE EXCEPTION 'Cannot downgrade while AUTO_APPLIED evidence exists; preserve or explicitly migrate it first';
        END IF;
    END $$""")
    op.drop_constraint("ck_extracted_fields_confirmation", "extracted_fields", schema="valuation")
    op.drop_constraint("ck_extracted_fields_status", "extracted_fields", schema="valuation")
    constraints(False)
