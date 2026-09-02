"""Add immutable valuation-to-review submission handoff snapshots.

Revision ID: 20260901_0012
Revises: 20260901_0011
Create Date: 2026-09-02
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260901_0012"
down_revision: Union[str, Sequence[str], None] = "20260901_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE valuation.review_submissions (
            submission_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            review_id uuid NOT NULL,
            case_id uuid NOT NULL,
            submission_no integer NOT NULL,
            submitted_by_user_id uuid NOT NULL,
            submitted_at timestamptz NOT NULL DEFAULT now(),
            source_validation_run_id uuid NOT NULL,
            source_report_document_id uuid NOT NULL,
            input_snapshot jsonb NOT NULL,
            input_fingerprint char(64) NOT NULL,
            supersedes_submission_id uuid,
            request_id uuid NOT NULL,
            CONSTRAINT fk_review_submissions_review
                FOREIGN KEY (review_id)
                REFERENCES review.reviews(review_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_review_submissions_case
                FOREIGN KEY (case_id)
                REFERENCES valuation.cases(case_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_review_submissions_submitted_by
                FOREIGN KEY (submitted_by_user_id)
                REFERENCES auth.users(user_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_review_submissions_source_validation_run
                FOREIGN KEY (source_validation_run_id)
                REFERENCES valuation.validation_runs(validation_run_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_review_submissions_source_report_document
                FOREIGN KEY (source_report_document_id)
                REFERENCES valuation.documents(document_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT uq_review_submissions_review_no
                UNIQUE (review_id, submission_no),
            CONSTRAINT uq_review_submissions_case_request
                UNIQUE (case_id, request_id),
            CONSTRAINT uq_review_submissions_review_id
                UNIQUE (review_id, submission_id),
            CONSTRAINT ck_review_submissions_submission_no
                CHECK (submission_no > 0),
            CONSTRAINT ck_review_submissions_fingerprint
                CHECK (input_fingerprint ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_review_submissions_input_snapshot
                CHECK (jsonb_typeof(input_snapshot) = 'object'),
            CONSTRAINT fk_review_submissions_supersedes
                FOREIGN KEY (review_id, supersedes_submission_id)
                REFERENCES valuation.review_submissions(review_id, submission_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        )
        """
    )

    op.execute("ALTER TABLE review.reviews ADD COLUMN latest_submission_id uuid")
    op.execute(
        """
        ALTER TABLE review.reviews
        ADD CONSTRAINT fk_reviews_latest_submission
            FOREIGN KEY (latest_submission_id)
            REFERENCES valuation.review_submissions(submission_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
        """
    )

    op.execute("ALTER TABLE valuation.validation_runs ADD COLUMN submission_id uuid")
    op.execute(
        "CREATE INDEX idx_validation_runs_submission "
        "ON valuation.validation_runs(submission_id)"
    )
    op.execute(
        """
        ALTER TABLE valuation.validation_runs
        ADD CONSTRAINT fk_validation_runs_submission
            FOREIGN KEY (submission_id)
            REFERENCES valuation.review_submissions(submission_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
        """
    )

    op.execute("ALTER TABLE valuation.cases DROP CONSTRAINT ck_cases_status")
    op.execute(
        """
        ALTER TABLE valuation.cases
        ADD CONSTRAINT ck_cases_status CHECK (
            case_status IN (
                'DRAFT', 'PROCESSING', 'REVIEWING', 'CORRECTION',
                'COMPLETED', 'ARCHIVED', 'IN_REVIEW',
                'REVISION_REQUIRED', 'REVIEW_COMPLETED'
            )
        )
        """
    )

    op.execute(
        """
        CREATE FUNCTION valuation.prevent_review_submission_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF pg_has_role(current_user, 'land_valuation_app', 'MEMBER') THEN
                RAISE EXCEPTION 'review submissions are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_review_submissions_immutable
        BEFORE UPDATE OR DELETE ON valuation.review_submissions
        FOR EACH ROW
        EXECUTE FUNCTION valuation.prevent_review_submission_mutation()
        """
    )

    # The integration/runtime role must reach the table so mutation attempts
    # are rejected by the immutability trigger instead of by incidental ACLs.
    op.execute("GRANT USAGE ON SCHEMA valuation TO land_valuation_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON valuation.review_submissions "
        "TO land_valuation_app"
    )


def downgrade() -> None:
    # Hold these locks until the migration transaction ends.  This closes the
    # gap between the data-loss guard and the destructive reverse DDL.
    op.execute(
        "LOCK TABLE valuation.review_submissions, valuation.validation_runs, "
        "review.reviews, valuation.cases IN SHARE ROW EXCLUSIVE MODE"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM valuation.review_submissions) THEN
                RAISE EXCEPTION 'cannot downgrade while review submissions exist';
            END IF;
        END
        $$
        """
    )

    op.execute(
        "DROP TRIGGER trg_review_submissions_immutable "
        "ON valuation.review_submissions"
    )
    op.execute("DROP FUNCTION valuation.prevent_review_submission_mutation()")

    op.execute(
        "ALTER TABLE valuation.cases DROP CONSTRAINT ck_cases_status"
    )
    op.execute(
        """
        ALTER TABLE valuation.cases
        ADD CONSTRAINT ck_cases_status CHECK (
            case_status IN (
                'DRAFT', 'PROCESSING', 'REVIEWING', 'CORRECTION',
                'COMPLETED', 'ARCHIVED'
            )
        )
        """
    )

    op.execute(
        "ALTER TABLE valuation.validation_runs "
        "DROP CONSTRAINT fk_validation_runs_submission"
    )
    op.execute("DROP INDEX valuation.idx_validation_runs_submission")
    op.execute("ALTER TABLE valuation.validation_runs DROP COLUMN submission_id")

    op.execute(
        "ALTER TABLE review.reviews DROP CONSTRAINT fk_reviews_latest_submission"
    )
    op.execute("ALTER TABLE review.reviews DROP COLUMN latest_submission_id")

    op.execute("DROP TABLE valuation.review_submissions")
