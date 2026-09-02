"""Add canonical valuation extraction and assistant workflow tables.

Revision ID: 20260901_0009
Revises: 20260830_0008
Create Date: 2026-09-01
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260901_0009"
down_revision: Union[str, Sequence[str], None] = "20260830_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            has_non_demo_legacy_extractions boolean;
        BEGIN
            IF to_regclass('valuation.extraction_runs') IS NOT NULL THEN
                EXECUTE $legacy_guard$
                    SELECT EXISTS (
                        SELECT 1
                        FROM valuation.extraction_runs er
                        JOIN valuation.cases c ON c.case_id = er.case_id
                        WHERE c.case_no <> 'DEMO-REVIEW-001'
                    )
                $legacy_guard$
                INTO has_non_demo_legacy_extractions;

                IF has_non_demo_legacy_extractions THEN
                    RAISE EXCEPTION 'non-demo legacy extraction data prevents migration';
                END IF;
            END IF;
        END
        $$;

        DELETE FROM review.correction_request_items
        WHERE correction_request_id IN (
            SELECT cr.correction_request_id
            FROM review.correction_requests cr
            JOIN review.reviews r ON r.review_id = cr.review_id
            JOIN valuation.cases c ON c.case_id = r.case_id
            WHERE c.case_no = 'DEMO-REVIEW-001'
        );
        DELETE FROM review.correction_requests
        WHERE review_id IN (
            SELECT r.review_id
            FROM review.reviews r
            JOIN valuation.cases c ON c.case_id = r.case_id
            WHERE c.case_no = 'DEMO-REVIEW-001'
        );
        DELETE FROM review.decisions
        WHERE review_id IN (
            SELECT r.review_id
            FROM review.reviews r
            JOIN valuation.cases c ON c.case_id = r.case_id
            WHERE c.case_no = 'DEMO-REVIEW-001'
        );
        DELETE FROM review.risk_summaries
        WHERE review_id IN (
            SELECT r.review_id
            FROM review.reviews r
            JOIN valuation.cases c ON c.case_id = r.case_id
            WHERE c.case_no = 'DEMO-REVIEW-001'
        );
        DELETE FROM review.findings
        WHERE review_id IN (
            SELECT r.review_id
            FROM review.reviews r
            JOIN valuation.cases c ON c.case_id = r.case_id
            WHERE c.case_no = 'DEMO-REVIEW-001'
        );
        DELETE FROM valuation.validation_findings
        WHERE validation_run_id IN (
            SELECT vr.validation_run_id
            FROM valuation.validation_runs vr
            JOIN valuation.cases c ON c.case_id = vr.case_id
            WHERE c.case_no = 'DEMO-REVIEW-001'
        );
        UPDATE review.reviews
        SET validation_run_id = NULL, latest_validation_run_id = NULL
        WHERE case_id IN (
            SELECT case_id FROM valuation.cases WHERE case_no = 'DEMO-REVIEW-001'
        );
        DELETE FROM review.missing_items
        WHERE review_id IN (
            SELECT r.review_id
            FROM review.reviews r
            JOIN valuation.cases c ON c.case_id = r.case_id
            WHERE c.case_no = 'DEMO-REVIEW-001'
        );
        DELETE FROM valuation.validation_runs
        WHERE case_id IN (
            SELECT case_id FROM valuation.cases WHERE case_no = 'DEMO-REVIEW-001'
        );
        DELETE FROM review.reviews
        WHERE case_id IN (
            SELECT case_id FROM valuation.cases WHERE case_no = 'DEMO-REVIEW-001'
        );
        DO $legacy_cleanup$
        BEGIN
            IF to_regclass('valuation.extracted_fields') IS NOT NULL
               AND to_regclass('valuation.extraction_runs') IS NOT NULL THEN
                EXECUTE $cleanup$
                    DELETE FROM valuation.extracted_fields
                    WHERE extraction_run_id IN (
                        SELECT er.extraction_run_id
                        FROM valuation.extraction_runs er
                        JOIN valuation.cases c ON c.case_id = er.case_id
                        WHERE c.case_no = 'DEMO-REVIEW-001'
                    )
                $cleanup$;
            END IF;

            IF to_regclass('valuation.extraction_runs') IS NOT NULL THEN
                EXECUTE $cleanup$
                    DELETE FROM valuation.extraction_runs
                    WHERE case_id IN (
                        SELECT case_id FROM valuation.cases WHERE case_no = 'DEMO-REVIEW-001'
                    )
                $cleanup$;
            END IF;
        END
        $legacy_cleanup$;

        DROP TABLE IF EXISTS valuation.extracted_fields;
        DROP TABLE IF EXISTS valuation.extraction_runs;
        DROP TABLE IF EXISTS valuation.document_extractions;
        """
    )
    op.execute(
        """
        CREATE TABLE valuation.document_extractions (
            extraction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id uuid NOT NULL,
            document_id uuid NOT NULL,
            provider varchar(30) NOT NULL,
            extraction_status varchar(20) NOT NULL DEFAULT 'PENDING',
            extracted_text text,
            page_count integer,
            error_message text,
            created_by_user_id uuid NOT NULL,
            started_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_document_extractions_case
                FOREIGN KEY (case_id) REFERENCES valuation.cases(case_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_document_extractions_document_same_case
                FOREIGN KEY (case_id, document_id)
                REFERENCES valuation.documents(case_id, document_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_document_extractions_user
                FOREIGN KEY (created_by_user_id) REFERENCES auth.users(user_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT uq_document_extractions_case_extraction
                UNIQUE (case_id, extraction_id),
            CONSTRAINT ck_document_extractions_provider
                CHECK (provider IN ('LOCAL_PDF', 'LOCAL_OCR', 'LOCAL_XLSX', 'TEXTRACT')),
            CONSTRAINT ck_document_extractions_status
                CHECK (extraction_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
            CONSTRAINT ck_document_extractions_pages
                CHECK (page_count IS NULL OR page_count > 0),
            CONSTRAINT ck_document_extractions_completion CHECK (
                (extraction_status IN ('PENDING', 'PROCESSING') AND completed_at IS NULL)
                OR (extraction_status IN ('COMPLETED', 'FAILED') AND completed_at IS NOT NULL)
            )
        );
        CREATE INDEX idx_document_extractions_document
            ON valuation.document_extractions(case_id, document_id, created_at DESC);

        CREATE TABLE valuation.extracted_fields (
            extracted_field_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id uuid NOT NULL,
            extraction_id uuid NOT NULL,
            document_id uuid NOT NULL,
            form_code varchar(10) NOT NULL,
            field_name varchar(100) NOT NULL,
            extracted_value jsonb NOT NULL,
            confidence numeric(5,4) NOT NULL,
            source_page integer,
            source_text text,
            analysis_provider varchar(20) NOT NULL DEFAULT 'RULE',
            model_id varchar(200),
            prompt_version varchar(100),
            field_status varchar(30) NOT NULL DEFAULT 'EXTRACTED',
            confirmed_value jsonb,
            confirmed_by_user_id uuid,
            confirmed_at timestamptz,
            applied_form_instance_id uuid,
            applied_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_extracted_fields_extraction_same_case
                FOREIGN KEY (case_id, extraction_id)
                REFERENCES valuation.document_extractions(case_id, extraction_id)
                ON UPDATE RESTRICT ON DELETE CASCADE,
            CONSTRAINT fk_extracted_fields_document_same_case
                FOREIGN KEY (case_id, document_id)
                REFERENCES valuation.documents(case_id, document_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_extracted_fields_confirmed_by
                FOREIGN KEY (confirmed_by_user_id) REFERENCES auth.users(user_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_extracted_fields_form_same_case
                FOREIGN KEY (case_id, applied_form_instance_id)
                REFERENCES valuation.form_instances(case_id, form_instance_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT uq_extracted_fields_extraction_form_field
                UNIQUE (extraction_id, form_code, field_name),
            CONSTRAINT ck_extracted_fields_form_code
                CHECK (form_code IN ('F01', 'F02', 'F02-RF', 'F03', 'F04')),
            CONSTRAINT ck_extracted_fields_name CHECK (length(btrim(field_name)) > 0),
            CONSTRAINT ck_extracted_fields_confidence CHECK (confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_extracted_fields_page CHECK (source_page IS NULL OR source_page > 0),
            CONSTRAINT ck_extracted_fields_analysis_provider
                CHECK (analysis_provider IN ('RULE', 'BEDROCK', 'CODEX')),
            CONSTRAINT ck_extracted_fields_analysis_provenance CHECK (
                (analysis_provider = 'RULE' AND model_id IS NULL AND prompt_version IS NULL)
                OR (analysis_provider IN ('BEDROCK', 'CODEX')
                    AND nullif(btrim(model_id), '') IS NOT NULL
                    AND nullif(btrim(prompt_version), '') IS NOT NULL)
            ),
            CONSTRAINT ck_extracted_fields_status CHECK (
                field_status IN ('EXTRACTED', 'NEEDS_CONFIRMATION', 'CONFIRMED', 'REJECTED', 'APPLIED')
            ),
            CONSTRAINT ck_extracted_fields_confirmation CHECK (
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
            )
        );
        CREATE INDEX idx_extracted_fields_case_status
            ON valuation.extracted_fields(case_id, form_code, field_status);
        CREATE TRIGGER trg_extracted_fields_updated_at
            BEFORE UPDATE ON valuation.extracted_fields
            FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();
        """
    )
    op.execute(
        """
        CREATE TABLE valuation.assistant_sessions (
            assistant_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id uuid NOT NULL,
            user_id uuid NOT NULL,
            form_instance_id uuid,
            current_step varchar(40) NOT NULL DEFAULT 'COLLECT_FIELDS',
            selected_form_type varchar(10) NOT NULL DEFAULT 'F03',
            missing_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
            missing_documents jsonb NOT NULL DEFAULT '[]'::jsonb,
            last_tool_name varchar(100),
            last_tool_status varchar(20),
            provider varchar(20) NOT NULL DEFAULT 'MOCK',
            model_id varchar(200) NOT NULL,
            prompt_version varchar(100) NOT NULL,
            session_status varchar(20) NOT NULL DEFAULT 'ACTIVE',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_assistant_sessions_case
                FOREIGN KEY (case_id) REFERENCES valuation.cases(case_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_assistant_sessions_user
                FOREIGN KEY (user_id) REFERENCES auth.users(user_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_assistant_sessions_form_same_case
                FOREIGN KEY (case_id, form_instance_id)
                REFERENCES valuation.form_instances(case_id, form_instance_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT ck_assistant_sessions_step CHECK (
                current_step IN ('COLLECT_FIELDS', 'COLLECT_DOCUMENTS', 'REVIEW_EXTRACTION', 'READY_TO_SUBMIT')
            ),
            CONSTRAINT ck_assistant_sessions_form CHECK (selected_form_type = 'F03'),
            CONSTRAINT ck_assistant_sessions_json CHECK (
                jsonb_typeof(missing_fields) = 'array' AND jsonb_typeof(missing_documents) = 'array'
            ),
            CONSTRAINT ck_assistant_sessions_tool_status CHECK (
                last_tool_status IS NULL OR last_tool_status IN ('PENDING', 'SUCCESS', 'FAILED')
            ),
            CONSTRAINT ck_assistant_sessions_provider CHECK (provider IN ('MOCK', 'BEDROCK')),
            CONSTRAINT ck_assistant_sessions_status CHECK (
                session_status IN ('ACTIVE', 'COMPLETED', 'FAILED', 'ARCHIVED')
            )
        );
        CREATE INDEX idx_assistant_sessions_case_user
            ON valuation.assistant_sessions(case_id, user_id, updated_at DESC);
        CREATE TRIGGER trg_assistant_sessions_updated_at
            BEFORE UPDATE ON valuation.assistant_sessions
            FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();

        CREATE TABLE valuation.assistant_messages (
            assistant_message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            assistant_session_id uuid NOT NULL,
            message_no integer NOT NULL,
            role varchar(20) NOT NULL,
            content text NOT NULL,
            tool_name varchar(100),
            tool_input_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            tool_result_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            request_id uuid,
            model_id varchar(200),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_assistant_messages_session
                FOREIGN KEY (assistant_session_id)
                REFERENCES valuation.assistant_sessions(assistant_session_id)
                ON UPDATE RESTRICT ON DELETE CASCADE,
            CONSTRAINT uq_assistant_messages_no UNIQUE (assistant_session_id, message_no),
            CONSTRAINT ck_assistant_messages_no CHECK (message_no > 0),
            CONSTRAINT ck_assistant_messages_role CHECK (role IN ('USER', 'ASSISTANT', 'TOOL')),
            CONSTRAINT ck_assistant_messages_content CHECK (length(btrim(content)) > 0),
            CONSTRAINT ck_assistant_messages_tool CHECK (
                (role = 'TOOL' AND tool_name IS NOT NULL)
                OR (role <> 'TOOL' AND tool_name IS NULL)
            )
        );
        CREATE INDEX idx_assistant_messages_session
            ON valuation.assistant_messages(assistant_session_id, message_no);

        COMMENT ON TABLE valuation.document_extractions IS '案件文件擷取工作；PDF 原檔仍只存 MinIO';
        COMMENT ON TABLE valuation.extracted_fields IS 'AI/OCR 候選欄位；確認前不可寫入正式表單';
        COMMENT ON TABLE valuation.assistant_sessions IS 'F03 AI 製作流程狀態；不保存模型思考過程';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM valuation.document_extractions)
               OR EXISTS (SELECT 1 FROM valuation.extracted_fields)
               OR EXISTS (SELECT 1 FROM valuation.assistant_sessions)
               OR EXISTS (SELECT 1 FROM valuation.assistant_messages) THEN
                RAISE EXCEPTION 'cannot downgrade canonical extraction schema while data exists';
            END IF;
        END
        $$;

        DROP TABLE valuation.assistant_messages;
        DROP TABLE valuation.assistant_sessions;
        DROP TABLE valuation.extracted_fields;
        DROP TABLE valuation.document_extractions;

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
            CONSTRAINT fk_extracted_fields_run FOREIGN KEY (extraction_run_id)
                REFERENCES valuation.extraction_runs(extraction_run_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_extracted_fields_verified_by FOREIGN KEY (verified_by_user_id)
                REFERENCES auth.users(user_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT uq_extracted_fields_run_path UNIQUE (extraction_run_id, field_code, field_path),
            CONSTRAINT ck_extracted_fields_type CHECK (value_type IN ('DECIMAL', 'TEXT', 'DATE', 'BOOLEAN', 'JSON')),
            CONSTRAINT ck_extracted_fields_page CHECK (page_number > 0),
            CONSTRAINT ck_extracted_fields_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            CONSTRAINT ck_extracted_fields_verification CHECK (verification_status IN ('AUTO_EXTRACTED', 'VERIFIED', 'REJECTED')),
            CONSTRAINT ck_extracted_fields_verifier CHECK (
                (verification_status = 'VERIFIED' AND verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL)
                OR (verification_status <> 'VERIFIED' AND verified_by_user_id IS NULL AND verified_at IS NULL)
            ),
            CONSTRAINT ck_extracted_fields_official CHECK (NOT is_official OR verification_status <> 'REJECTED'),
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
        """
    )
