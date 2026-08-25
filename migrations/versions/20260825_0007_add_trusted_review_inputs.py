"""Add trusted extraction inputs and rule applicability metadata.

Revision ID: 20260825_0007
Revises: 20260825_0006
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260825_0007"
down_revision: Union[str, Sequence[str], None] = "20260825_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM valuation.rule_versions WHERE status = 'PUBLISHED'
            ) THEN
                RAISE EXCEPTION
                    'published rule versions require an explicit knowledge source before 0007';
            END IF;
        END
        $$;

        CREATE TABLE valuation.extraction_runs (
            extraction_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id uuid NOT NULL,
            document_id uuid NOT NULL,
            document_version integer NOT NULL,
            run_no integer NOT NULL,
            status varchar(20) NOT NULL DEFAULT 'PENDING',
            extractor_name varchar(100) NOT NULL,
            extractor_version varchar(100),
            started_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz,
            error_code varchar(100),
            error_message text,
            CONSTRAINT fk_extraction_runs_document
                FOREIGN KEY (case_id, document_id)
                REFERENCES valuation.documents(case_id, document_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT uq_extraction_runs_document_version_run
                UNIQUE (document_id, document_version, run_no),
            CONSTRAINT ck_extraction_runs_document_version CHECK (document_version > 0),
            CONSTRAINT ck_extraction_runs_run_no CHECK (run_no > 0),
            CONSTRAINT ck_extraction_runs_status CHECK (
                status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')
            ),
            CONSTRAINT ck_extraction_runs_completion CHECK (
                (status IN ('PENDING', 'PROCESSING') AND completed_at IS NULL)
                OR (status = 'COMPLETED' AND completed_at IS NOT NULL
                    AND error_code IS NULL AND error_message IS NULL)
                OR (status = 'FAILED' AND completed_at IS NOT NULL
                    AND nullif(btrim(error_code), '') IS NOT NULL)
            ),
            CONSTRAINT ck_extraction_runs_times CHECK (
                completed_at IS NULL OR completed_at >= started_at
            )
        );

        CREATE TABLE valuation.extracted_fields (
            extracted_field_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            extraction_run_id uuid NOT NULL,
            field_code varchar(100) NOT NULL,
            field_path varchar(500) NOT NULL,
            value_type varchar(20) NOT NULL,
            raw_text text NOT NULL,
            normalized_value jsonb NOT NULL,
            page_number integer NOT NULL,
            bounding_box jsonb,
            confidence numeric(7,6),
            verification_status varchar(20) NOT NULL DEFAULT 'AUTO_EXTRACTED',
            verified_by_user_id uuid,
            verified_at timestamptz,
            is_official boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_extracted_fields_run
                FOREIGN KEY (extraction_run_id)
                REFERENCES valuation.extraction_runs(extraction_run_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_extracted_fields_verified_by
                FOREIGN KEY (verified_by_user_id) REFERENCES auth.users(user_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT uq_extracted_fields_run_path
                UNIQUE (extraction_run_id, field_code, field_path),
            CONSTRAINT ck_extracted_fields_type CHECK (
                value_type IN ('DECIMAL', 'TEXT', 'DATE', 'BOOLEAN', 'JSON')
            ),
            CONSTRAINT ck_extracted_fields_page CHECK (page_number > 0),
            CONSTRAINT ck_extracted_fields_confidence CHECK (
                confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
            ),
            CONSTRAINT ck_extracted_fields_verification CHECK (
                verification_status IN ('AUTO_EXTRACTED', 'VERIFIED', 'REJECTED')
            ),
            CONSTRAINT ck_extracted_fields_verifier CHECK (
                (verification_status = 'VERIFIED'
                    AND verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL)
                OR (verification_status <> 'VERIFIED'
                    AND verified_by_user_id IS NULL AND verified_at IS NULL)
            ),
            CONSTRAINT ck_extracted_fields_official CHECK (
                NOT is_official OR verification_status <> 'REJECTED'
            ),
            CONSTRAINT ck_extracted_fields_text CHECK (
                nullif(btrim(field_code), '') IS NOT NULL
                AND nullif(btrim(field_path), '') IS NOT NULL
                AND nullif(btrim(raw_text), '') IS NOT NULL
            )
        );

        CREATE INDEX idx_extraction_runs_document_latest
            ON valuation.extraction_runs(document_id, document_version, run_no DESC);
        CREATE INDEX idx_extracted_fields_run_official
            ON valuation.extracted_fields(extraction_run_id, field_code)
            WHERE is_official = true;

        ALTER TABLE valuation.rule_versions
            ADD COLUMN applicable_case_type varchar(50),
            ADD COLUMN applicable_district_code varchar(20),
            ADD COLUMN selection_priority integer NOT NULL DEFAULT 0,
            ADD CONSTRAINT ck_rule_versions_selection_priority
                CHECK (selection_priority >= 0),
            ADD CONSTRAINT ck_rule_versions_published_source CHECK (
                status <> 'PUBLISHED' OR source_document_id IS NOT NULL
            );

        CREATE INDEX idx_rule_versions_selection
            ON valuation.rule_versions(
                status, applicable_case_type, applicable_district_code,
                effective_from, selection_priority DESC
            );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX valuation.idx_rule_versions_selection;

        ALTER TABLE valuation.rule_versions
            DROP CONSTRAINT ck_rule_versions_published_source,
            DROP CONSTRAINT ck_rule_versions_selection_priority,
            DROP COLUMN selection_priority,
            DROP COLUMN applicable_district_code,
            DROP COLUMN applicable_case_type;

        DROP INDEX valuation.idx_extracted_fields_run_official;
        DROP INDEX valuation.idx_extraction_runs_document_latest;
        DROP TABLE valuation.extracted_fields;
        DROP TABLE valuation.extraction_runs;
        """
    )
