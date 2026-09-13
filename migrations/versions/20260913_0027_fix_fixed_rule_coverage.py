"""Make the fixed New Taipei formal rule cover the complete workflow.

Revision ID: 20260913_0027
Revises: 20260912_0026, 225d7539d1ff
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260913_0027"
down_revision: Union[str, Sequence[str], None] = (
    "20260912_0026",
    "225d7539d1ff",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The rule is fixed by the application, so it must not depend on the date
    # of the Demo seed or on the land-use type used by its sample case.
    op.execute(
        """
        UPDATE valuation.rule_versions
        SET effective_from = DATE '2020-01-01',
            effective_to = NULL,
            applicable_district_code = NULL,
            district_scope = '{"mode":"ALL","district_codes":[]}'::jsonb,
            land_use_types = '["RESIDENTIAL","COMMERCIAL","INDUSTRIAL","AGRICULTURAL","OTHER"]'::jsonb,
            notes = CASE
                WHEN notes IS NULL THEN 'Fixed New Taipei formal calculation rule'
                WHEN notes LIKE '%Fixed New Taipei formal calculation rule%' THEN notes
                ELSE notes || '; Fixed New Taipei formal calculation rule'
            END
        WHERE rule_set_code IN ('DEMO-F03-FORMAL-VALIDATION', 'F03_MVP_VALIDATION')
          AND status = 'PUBLISHED'
          AND formula_code = 'NTPC_COMPARISON_V1'
          AND rounding_code = 'NTPC_LAND_PRICE_V1'
        """
    )


def downgrade() -> None:
    # Applicability repair is intentionally not reversed: reverting it would
    # restore a seed-date-specific rule and make the fixed workflow fail again.
    pass
