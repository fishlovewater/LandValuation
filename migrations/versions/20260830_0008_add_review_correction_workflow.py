"""Add review correction-request workflow tables and triage-compatible constraints.

Revision ID: 20260830_0008
Revises: 20260825_0007
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260830_0008"
down_revision: Union[str, Sequence[str], None] = "20260825_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        -- Widen finding status so DISMISSED_FALSE_POSITIVE (24 chars) fits.
        ALTER TABLE review.findings ALTER COLUMN status TYPE varchar(30);

        CREATE TABLE review.correction_requests (
            correction_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            review_id uuid NOT NULL
                REFERENCES review.reviews(review_id) ON DELETE RESTRICT,
            request_no integer NOT NULL CHECK (request_no > 0),
            based_on_validation_run_id uuid NOT NULL
                REFERENCES valuation.validation_runs(validation_run_id) ON DELETE RESTRICT,
            status varchar(20) NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN ('DRAFT','SENT','RESUBMITTED','RECHECKING','RECHECKED')),
            due_at timestamptz NOT NULL,
            message text NOT NULL CHECK (nullif(btrim(message), '') IS NOT NULL),
            base_document_id uuid NOT NULL
                REFERENCES valuation.documents(document_id) ON DELETE RESTRICT,
            base_document_version integer NOT NULL CHECK (base_document_version > 0),
            response_document_id uuid
                REFERENCES valuation.documents(document_id) ON DELETE RESTRICT,
            response_document_version integer
                CHECK (response_document_version > base_document_version),
            created_by_user_id uuid NOT NULL
                REFERENCES auth.users(user_id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT now(),
            sent_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE RESTRICT,
            sent_at timestamptz,
            resubmitted_at timestamptz,
            rechecked_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE RESTRICT,
            rechecked_at timestamptz,
            UNIQUE (review_id, request_no),
            CONSTRAINT ck_correction_requests_response_pair CHECK (
                (response_document_id IS NULL AND response_document_version IS NULL)
                OR (response_document_id IS NOT NULL
                    AND response_document_version IS NOT NULL)
            ),
            CONSTRAINT ck_correction_requests_status_timeline CHECK (
                (status = 'DRAFT'
                    AND sent_at IS NULL AND sent_by_user_id IS NULL
                    AND response_document_id IS NULL AND resubmitted_at IS NULL
                    AND rechecked_by_user_id IS NULL AND rechecked_at IS NULL)
                OR (status = 'SENT'
                    AND sent_at IS NOT NULL AND sent_by_user_id IS NOT NULL
                    AND response_document_id IS NULL AND resubmitted_at IS NULL
                    AND rechecked_by_user_id IS NULL AND rechecked_at IS NULL)
                OR (status = 'RESUBMITTED'
                    AND sent_at IS NOT NULL AND sent_by_user_id IS NOT NULL
                    AND response_document_id IS NOT NULL AND resubmitted_at IS NOT NULL
                    AND rechecked_by_user_id IS NULL AND rechecked_at IS NULL)
                OR (status = 'RECHECKING'
                    AND sent_at IS NOT NULL AND sent_by_user_id IS NOT NULL
                    AND response_document_id IS NOT NULL AND resubmitted_at IS NOT NULL
                    AND rechecked_by_user_id IS NULL AND rechecked_at IS NULL)
                OR (status = 'RECHECKED'
                    AND sent_at IS NOT NULL AND sent_by_user_id IS NOT NULL
                    AND response_document_id IS NOT NULL AND resubmitted_at IS NOT NULL
                    AND rechecked_by_user_id IS NOT NULL AND rechecked_at IS NOT NULL)
            )
        );

        CREATE UNIQUE INDEX uq_review_correction_one_active
            ON review.correction_requests(review_id)
            WHERE status <> 'RECHECKED';

        CREATE TABLE review.correction_request_items (
            correction_request_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            correction_request_id uuid NOT NULL
                REFERENCES review.correction_requests(correction_request_id)
                ON DELETE RESTRICT,
            finding_id uuid NOT NULL
                REFERENCES review.findings(finding_id) ON DELETE RESTRICT,
            finding_code varchar(100) NOT NULL,
            finding_type varchar(50) NOT NULL,
            severity varchar(20) NOT NULL,
            document_id uuid REFERENCES valuation.documents(document_id) ON DELETE RESTRICT,
            document_version integer CHECK (document_version IS NULL OR document_version > 0),
            page_number integer CHECK (page_number IS NULL OR page_number > 0),
            reported_text text,
            reported_value text,
            legal_basis_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
            source_evidence_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
            issue_summary text NOT NULL CHECK (nullif(btrim(issue_summary), '') IS NOT NULL),
            requested_correction text NOT NULL
                CHECK (nullif(btrim(requested_correction), '') IS NOT NULL),
            recheck_outcome varchar(20) NOT NULL DEFAULT 'PENDING'
                CHECK (recheck_outcome IN
                    ('PENDING','RESOLVED','STILL_PRESENT','NOT_EVALUATED')),
            resulting_finding_id uuid
                REFERENCES review.findings(finding_id) ON DELETE RESTRICT,
            rechecked_at timestamptz,
            UNIQUE (correction_request_id, finding_id)
        );

        CREATE INDEX idx_correction_items_request_outcome
            ON review.correction_request_items(correction_request_id, recheck_outcome);

        CREATE TABLE review.urgency_settings (
            settings_id smallint PRIMARY KEY CHECK (settings_id = 1),
            urgent_days integer NOT NULL,
            due_soon_days integer NOT NULL,
            updated_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE RESTRICT,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (urgent_days >= 0 AND urgent_days < due_soon_days)
        );

        INSERT INTO review.urgency_settings(settings_id, urgent_days, due_soon_days)
        VALUES (1, 3, 7)
        ON CONFLICT (settings_id) DO NOTHING;
        """
    )

    # Supersede triage-compatible CHECK constraints while retaining legacy values.
    op.execute("ALTER TABLE review.findings DROP CONSTRAINT ck_findings_status")
    op.execute(
        """
        ALTER TABLE review.findings
        ADD CONSTRAINT ck_findings_status CHECK (
            status IN (
                'OPEN', 'CONFIRMED', 'REJECTED', 'CORRECTED', 'IGNORED',
                'ACCEPTED', 'PARTIALLY_ACCEPTED', 'RESOLVED',
                'REQUIRES_SUPPLEMENT', 'EXPERT_REVIEW',
                'CONFIRMED_ISSUE', 'DISMISSED_FALSE_POSITIVE'
            )
        )
        """
    )

    op.execute("ALTER TABLE review.decisions DROP CONSTRAINT ck_decisions_value")
    op.execute(
        """
        ALTER TABLE review.decisions
        ADD CONSTRAINT ck_decisions_value CHECK (
            decision IN (
                'ACCEPT', 'REJECT', 'REQUEST_CORRECTION', 'WAIVE',
                'ACCEPTED', 'PARTIALLY_ACCEPTED', 'REJECTED',
                'REQUIRES_SUPPLEMENT', 'EXPERT_REVIEW', 'APPROVED',
                'RETURNED_FOR_REVISION', 'SUPPLEMENT_REQUIRED', 'REVIEW_COMPLETED',
                'CONFIRMED_ISSUE', 'DISMISSED_FALSE_POSITIVE'
            )
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        -- Fail closed if any correction data or new triage values exist.
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM review.correction_requests) THEN
                RAISE EXCEPTION 'cannot downgrade: correction_requests has rows';
            END IF;
            IF EXISTS (
                SELECT 1 FROM review.findings
                WHERE status IN ('CONFIRMED_ISSUE', 'DISMISSED_FALSE_POSITIVE')
            ) THEN
                RAISE EXCEPTION 'cannot downgrade: findings use new triage status';
            END IF;
            IF EXISTS (
                SELECT 1 FROM review.decisions
                WHERE decision IN ('CONFIRMED_ISSUE', 'DISMISSED_FALSE_POSITIVE')
            ) THEN
                RAISE EXCEPTION 'cannot downgrade: decisions use new triage value';
            END IF;
        END
        $$;

        DROP TABLE review.correction_request_items;
        DROP INDEX IF EXISTS review.uq_review_correction_one_active;
        DROP TABLE review.correction_requests;
        DROP TABLE review.urgency_settings;
        """
    )

    op.execute("ALTER TABLE review.decisions DROP CONSTRAINT ck_decisions_value")
    op.execute(
        """
        ALTER TABLE review.decisions
        ADD CONSTRAINT ck_decisions_value CHECK (
            decision IN (
                'ACCEPT', 'REJECT', 'REQUEST_CORRECTION', 'WAIVE',
                'ACCEPTED', 'PARTIALLY_ACCEPTED', 'REJECTED',
                'REQUIRES_SUPPLEMENT', 'EXPERT_REVIEW', 'APPROVED',
                'RETURNED_FOR_REVISION', 'SUPPLEMENT_REQUIRED', 'REVIEW_COMPLETED'
            )
        )
        """
    )

    op.execute("ALTER TABLE review.findings DROP CONSTRAINT ck_findings_status")
    op.execute(
        """
        ALTER TABLE review.findings
        ADD CONSTRAINT ck_findings_status CHECK (
            status IN (
                'OPEN', 'CONFIRMED', 'REJECTED', 'CORRECTED', 'IGNORED',
                'ACCEPTED', 'PARTIALLY_ACCEPTED', 'RESOLVED',
                'REQUIRES_SUPPLEMENT', 'EXPERT_REVIEW'
            )
        );
        ALTER TABLE review.findings ALTER COLUMN status TYPE varchar(20);
        """
    )
