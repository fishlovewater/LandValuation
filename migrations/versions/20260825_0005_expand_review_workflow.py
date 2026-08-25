"""Expand the existing review workflow for subsystem two.

Revision ID: 20260825_0005
Revises: 20260824_0004
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260825_0005"
down_revision: Union[str, Sequence[str], None] = "20260824_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE review.reviews
        ADD COLUMN received_at timestamptz NOT NULL DEFAULT now(),
        ADD COLUMN due_at timestamptz,
        ADD COLUMN assigned_reviewer_id uuid,
        ADD COLUMN manual_priority integer NOT NULL DEFAULT 0,
        ADD COLUMN manual_priority_reason text,
        ADD COLUMN current_risk_level varchar(20),
        ADD COLUMN high_count integer NOT NULL DEFAULT 0,
        ADD COLUMN medium_count integer NOT NULL DEFAULT 0,
        ADD COLUMN low_count integer NOT NULL DEFAULT 0,
        ADD COLUMN missing_item_count integer NOT NULL DEFAULT 0,
        ADD COLUMN latest_validation_run_id uuid
        """
    )
    op.execute(
        """
        ALTER TABLE review.reviews
        ADD CONSTRAINT fk_reviews_assigned_reviewer
            FOREIGN KEY (assigned_reviewer_id) REFERENCES auth.users(user_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        ADD CONSTRAINT ck_reviews_due_at
            CHECK (due_at IS NULL OR due_at >= received_at),
        ADD CONSTRAINT ck_reviews_manual_priority
            CHECK (manual_priority BETWEEN 0 AND 100),
        ADD CONSTRAINT ck_reviews_counts
            CHECK (high_count >= 0 AND medium_count >= 0 AND low_count >= 0 AND missing_item_count >= 0),
        ADD CONSTRAINT ck_reviews_current_risk
            CHECK (current_risk_level IS NULL OR current_risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))
        """
    )
    op.execute("ALTER TABLE review.reviews DROP CONSTRAINT ck_reviews_status")
    op.execute(
        """
        ALTER TABLE review.reviews
        ADD CONSTRAINT ck_reviews_status CHECK (
            review_status IN (
                'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED',
                'RECEIVED', 'PREPROCESSING', 'PENDING_MATERIALS',
                'READY_FOR_REVIEW', 'ANALYZING', 'REVIEW_REQUIRED',
                'RETURNED_FOR_REVISION', 'SUPPLEMENT_REQUIRED',
                'EXPERT_REVIEW', 'APPROVED', 'REVIEW_COMPLETED'
            )
        )
        """
    )

    op.execute(
        """
        ALTER TABLE valuation.validation_runs
        ADD COLUMN review_id uuid,
        ADD COLUMN run_no integer,
        ADD COLUMN input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN model_id varchar(200),
        ADD COLUMN prompt_version varchar(100),
        ADD COLUMN error_code varchar(100),
        ADD COLUMN error_message text
        """
    )
    op.execute(
        """
        ALTER TABLE valuation.validation_runs
        ADD CONSTRAINT fk_validation_runs_review
            FOREIGN KEY (review_id) REFERENCES review.reviews(review_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        ADD CONSTRAINT ck_validation_runs_run_no
            CHECK (run_no IS NULL OR run_no > 0),
        ADD CONSTRAINT uq_validation_runs_review_run_no
            UNIQUE (review_id, run_no)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_validation_runs_one_running_review
        ON valuation.validation_runs(review_id)
        WHERE review_id IS NOT NULL AND run_status = 'RUNNING'
        """
    )
    op.execute(
        """
        ALTER TABLE review.reviews
        ADD CONSTRAINT fk_reviews_latest_validation_run
            FOREIGN KEY (latest_validation_run_id)
            REFERENCES valuation.validation_runs(validation_run_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
        """
    )

    op.execute("ALTER TABLE review.findings DROP CONSTRAINT findings_review_id_finding_code_key")
    op.execute(
        """
        ALTER TABLE review.findings
        ADD COLUMN validation_run_id uuid,
        ADD COLUMN document_id uuid,
        ADD COLUMN document_version integer,
        ADD COLUMN page_number integer,
        ADD COLUMN field_path text,
        ADD COLUMN bounding_box jsonb,
        ADD COLUMN source_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
        ADD COLUMN reported_text text,
        ADD COLUMN reported_value text,
        ADD COLUMN legal_basis jsonb NOT NULL DEFAULT '[]'::jsonb,
        ADD COLUMN reported_grade varchar(100),
        ADD COLUMN system_grade varchar(100),
        ADD COLUMN reported_adjustment_rate numeric(12,6),
        ADD COLUMN system_adjustment_rate numeric(12,6),
        ADD COLUMN comparison_result jsonb NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN recommended_action jsonb NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN ai_reasoning_summary text,
        ADD COLUMN ai_confidence numeric(5,4),
        ADD COLUMN ai_status varchar(40) NOT NULL DEFAULT 'NOT_REQUESTED',
        ADD COLUMN supersedes_finding_id uuid,
        ADD COLUMN rule_version_id uuid
        """
    )
    op.execute(
        """
        ALTER TABLE review.findings
        ADD CONSTRAINT fk_review_findings_validation_run
            FOREIGN KEY (validation_run_id)
            REFERENCES valuation.validation_runs(validation_run_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        ADD CONSTRAINT fk_review_findings_document
            FOREIGN KEY (document_id) REFERENCES valuation.documents(document_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        ADD CONSTRAINT fk_review_findings_supersedes
            FOREIGN KEY (supersedes_finding_id) REFERENCES review.findings(finding_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        ADD CONSTRAINT fk_review_findings_rule_version
            FOREIGN KEY (rule_version_id) REFERENCES valuation.rule_versions(rule_version_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        ADD CONSTRAINT uq_review_findings_run_code
            UNIQUE (review_id, validation_run_id, finding_code),
        ADD CONSTRAINT ck_review_findings_document_version
            CHECK (document_version IS NULL OR document_version > 0),
        ADD CONSTRAINT ck_review_findings_page_number
            CHECK (page_number IS NULL OR page_number > 0),
        ADD CONSTRAINT ck_review_findings_ai_confidence
            CHECK (ai_confidence IS NULL OR ai_confidence BETWEEN 0 AND 1),
        ADD CONSTRAINT ck_review_findings_ai_status
            CHECK (ai_status IN ('NOT_REQUESTED', 'AVAILABLE', 'AI_EXPLANATION_UNAVAILABLE', 'INVALID'))
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
        )
        """
    )

    op.execute(
        """
        ALTER TABLE review.decisions
        ADD COLUMN request_id uuid,
        ADD COLUMN before_value jsonb,
        ADD COLUMN after_value jsonb
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

    op.execute("ALTER TABLE review.missing_items DROP CONSTRAINT missing_items_review_id_item_code_key")
    op.execute(
        """
        ALTER TABLE review.missing_items
        ADD COLUMN validation_run_id uuid,
        ADD COLUMN field_path text,
        ADD COLUMN reason text,
        ADD COLUMN affected_rule_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
        ADD COLUMN due_at timestamptz,
        ADD COLUMN notified_at timestamptz,
        ADD COLUMN notification_status varchar(30),
        ADD COLUMN created_at timestamptz NOT NULL DEFAULT now()
        """
    )
    op.execute(
        """
        ALTER TABLE review.missing_items
        ADD CONSTRAINT fk_missing_items_validation_run
            FOREIGN KEY (validation_run_id)
            REFERENCES valuation.validation_runs(validation_run_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        ADD CONSTRAINT uq_missing_items_run_code
            UNIQUE (review_id, validation_run_id, item_code),
        ADD CONSTRAINT ck_missing_items_notification_status
            CHECK (notification_status IS NULL OR notification_status IN ('PENDING', 'SENT', 'FAILED', 'ACKNOWLEDGED')),
        ADD CONSTRAINT ck_missing_items_due_at
            CHECK (due_at IS NULL OR due_at >= created_at)
        """
    )

    op.execute("ALTER TABLE review.risk_summaries DROP CONSTRAINT risk_summaries_review_id_key")
    op.execute(
        """
        ALTER TABLE review.risk_summaries
        ADD COLUMN validation_run_id uuid,
        ADD COLUMN high_count integer NOT NULL DEFAULT 0,
        ADD COLUMN medium_count integer NOT NULL DEFAULT 0,
        ADD COLUMN low_count integer NOT NULL DEFAULT 0,
        ADD COLUMN missing_item_count integer NOT NULL DEFAULT 0,
        ADD COLUMN risk_reasons jsonb NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE review.risk_summaries
        ADD CONSTRAINT fk_risk_summaries_validation_run
            FOREIGN KEY (validation_run_id)
            REFERENCES valuation.validation_runs(validation_run_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        ADD CONSTRAINT uq_risk_summaries_review_run
            UNIQUE (review_id, validation_run_id),
        ADD CONSTRAINT ck_risk_summaries_counts
            CHECK (high_count >= 0 AND medium_count >= 0 AND low_count >= 0 AND missing_item_count >= 0)
        """
    )

    op.execute(
        "CREATE INDEX idx_reviews_queue ON review.reviews(manual_priority DESC, due_at, received_at)"
    )
    op.execute(
        "CREATE INDEX idx_reviews_assignment_status ON review.reviews(assigned_reviewer_id, review_status, due_at)"
    )
    op.execute(
        "CREATE INDEX idx_review_findings_run_status ON review.findings(validation_run_id, status, severity)"
    )
    op.execute(
        "CREATE INDEX idx_review_decisions_request_id ON review.decisions(request_id) WHERE request_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_missing_items_open ON review.missing_items(review_id, status, due_at) WHERE status = 'OPEN'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS review.idx_missing_items_open")
    op.execute("DROP INDEX IF EXISTS review.idx_review_decisions_request_id")
    op.execute("DROP INDEX IF EXISTS review.idx_review_findings_run_status")
    op.execute("DROP INDEX IF EXISTS review.idx_reviews_assignment_status")
    op.execute("DROP INDEX IF EXISTS review.idx_reviews_queue")

    op.execute("ALTER TABLE review.risk_summaries DROP CONSTRAINT ck_risk_summaries_counts")
    op.execute("ALTER TABLE review.risk_summaries DROP CONSTRAINT uq_risk_summaries_review_run")
    op.execute("ALTER TABLE review.risk_summaries DROP CONSTRAINT fk_risk_summaries_validation_run")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT review_id FROM review.risk_summaries
                GROUP BY review_id HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'multiple risk summaries per review prevent downgrade';
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        ALTER TABLE review.risk_summaries
        DROP COLUMN risk_reasons,
        DROP COLUMN missing_item_count,
        DROP COLUMN low_count,
        DROP COLUMN medium_count,
        DROP COLUMN high_count,
        DROP COLUMN validation_run_id,
        ADD CONSTRAINT risk_summaries_review_id_key UNIQUE (review_id)
        """
    )

    op.execute("ALTER TABLE review.missing_items DROP CONSTRAINT ck_missing_items_due_at")
    op.execute("ALTER TABLE review.missing_items DROP CONSTRAINT ck_missing_items_notification_status")
    op.execute("ALTER TABLE review.missing_items DROP CONSTRAINT uq_missing_items_run_code")
    op.execute("ALTER TABLE review.missing_items DROP CONSTRAINT fk_missing_items_validation_run")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT review_id, item_code FROM review.missing_items
                GROUP BY review_id, item_code HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'repeated missing item history prevents downgrade';
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        ALTER TABLE review.missing_items
        DROP COLUMN created_at,
        DROP COLUMN notification_status,
        DROP COLUMN notified_at,
        DROP COLUMN due_at,
        DROP COLUMN affected_rule_codes,
        DROP COLUMN reason,
        DROP COLUMN field_path,
        DROP COLUMN validation_run_id,
        ADD CONSTRAINT missing_items_review_id_item_code_key UNIQUE (review_id, item_code)
        """
    )

    op.execute("ALTER TABLE review.decisions DROP CONSTRAINT ck_decisions_value")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM review.decisions
                WHERE decision NOT IN ('ACCEPT', 'REJECT', 'REQUEST_CORRECTION', 'WAIVE')
            ) THEN
                RAISE EXCEPTION 'new decision values prevent downgrade';
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        ALTER TABLE review.decisions
        DROP COLUMN after_value,
        DROP COLUMN before_value,
        DROP COLUMN request_id,
        ADD CONSTRAINT ck_decisions_value
            CHECK (decision IN ('ACCEPT', 'REJECT', 'REQUEST_CORRECTION', 'WAIVE'))
        """
    )

    op.execute("ALTER TABLE review.findings DROP CONSTRAINT ck_findings_status")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM review.findings
                WHERE status NOT IN ('OPEN', 'CONFIRMED', 'REJECTED', 'CORRECTED', 'IGNORED')
            ) THEN
                RAISE EXCEPTION 'new finding statuses prevent downgrade';
            END IF;
            IF EXISTS (
                SELECT review_id, finding_code FROM review.findings
                GROUP BY review_id, finding_code HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'repeated finding history prevents downgrade';
            END IF;
        END
        $$
        """
    )
    op.execute("ALTER TABLE review.findings DROP CONSTRAINT ck_review_findings_ai_status")
    op.execute("ALTER TABLE review.findings DROP CONSTRAINT ck_review_findings_ai_confidence")
    op.execute("ALTER TABLE review.findings DROP CONSTRAINT ck_review_findings_page_number")
    op.execute("ALTER TABLE review.findings DROP CONSTRAINT ck_review_findings_document_version")
    op.execute("ALTER TABLE review.findings DROP CONSTRAINT uq_review_findings_run_code")
    op.execute("ALTER TABLE review.findings DROP CONSTRAINT fk_review_findings_rule_version")
    op.execute("ALTER TABLE review.findings DROP CONSTRAINT fk_review_findings_supersedes")
    op.execute("ALTER TABLE review.findings DROP CONSTRAINT fk_review_findings_document")
    op.execute("ALTER TABLE review.findings DROP CONSTRAINT fk_review_findings_validation_run")
    op.execute(
        """
        ALTER TABLE review.findings
        DROP COLUMN rule_version_id,
        DROP COLUMN supersedes_finding_id,
        DROP COLUMN ai_status,
        DROP COLUMN ai_confidence,
        DROP COLUMN ai_reasoning_summary,
        DROP COLUMN recommended_action,
        DROP COLUMN comparison_result,
        DROP COLUMN system_adjustment_rate,
        DROP COLUMN reported_adjustment_rate,
        DROP COLUMN system_grade,
        DROP COLUMN reported_grade,
        DROP COLUMN legal_basis,
        DROP COLUMN reported_value,
        DROP COLUMN reported_text,
        DROP COLUMN source_evidence,
        DROP COLUMN bounding_box,
        DROP COLUMN field_path,
        DROP COLUMN page_number,
        DROP COLUMN document_version,
        DROP COLUMN document_id,
        DROP COLUMN validation_run_id,
        ADD CONSTRAINT findings_review_id_finding_code_key UNIQUE (review_id, finding_code),
        ADD CONSTRAINT ck_findings_status
            CHECK (status IN ('OPEN', 'CONFIRMED', 'REJECTED', 'CORRECTED', 'IGNORED'))
        """
    )

    op.execute("ALTER TABLE review.reviews DROP CONSTRAINT fk_reviews_latest_validation_run")
    op.execute("DROP INDEX IF EXISTS valuation.uq_validation_runs_one_running_review")
    op.execute("ALTER TABLE valuation.validation_runs DROP CONSTRAINT uq_validation_runs_review_run_no")
    op.execute("ALTER TABLE valuation.validation_runs DROP CONSTRAINT ck_validation_runs_run_no")
    op.execute("ALTER TABLE valuation.validation_runs DROP CONSTRAINT fk_validation_runs_review")
    op.execute(
        """
        ALTER TABLE valuation.validation_runs
        DROP COLUMN error_message,
        DROP COLUMN error_code,
        DROP COLUMN prompt_version,
        DROP COLUMN model_id,
        DROP COLUMN input_snapshot,
        DROP COLUMN run_no,
        DROP COLUMN review_id
        """
    )

    op.execute("ALTER TABLE review.reviews DROP CONSTRAINT ck_reviews_status")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM review.reviews
                WHERE review_status NOT IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')
            ) THEN
                RAISE EXCEPTION 'new review statuses prevent downgrade';
            END IF;
        END
        $$
        """
    )
    op.execute("ALTER TABLE review.reviews DROP CONSTRAINT ck_reviews_current_risk")
    op.execute("ALTER TABLE review.reviews DROP CONSTRAINT ck_reviews_counts")
    op.execute("ALTER TABLE review.reviews DROP CONSTRAINT ck_reviews_manual_priority")
    op.execute("ALTER TABLE review.reviews DROP CONSTRAINT ck_reviews_due_at")
    op.execute("ALTER TABLE review.reviews DROP CONSTRAINT fk_reviews_assigned_reviewer")
    op.execute(
        """
        ALTER TABLE review.reviews
        DROP COLUMN latest_validation_run_id,
        DROP COLUMN missing_item_count,
        DROP COLUMN low_count,
        DROP COLUMN medium_count,
        DROP COLUMN high_count,
        DROP COLUMN current_risk_level,
        DROP COLUMN manual_priority_reason,
        DROP COLUMN manual_priority,
        DROP COLUMN assigned_reviewer_id,
        DROP COLUMN due_at,
        DROP COLUMN received_at,
        ADD CONSTRAINT ck_reviews_status
            CHECK (review_status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'))
        """
    )
