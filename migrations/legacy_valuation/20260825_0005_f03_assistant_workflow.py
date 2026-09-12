"""Add F03 document extraction and assistant workflow state.

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
                CHECK (provider IN ('LOCAL_PDF', 'TEXTRACT')),
            CONSTRAINT ck_document_extractions_status
                CHECK (extraction_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
            CONSTRAINT ck_document_extractions_pages
                CHECK (page_count IS NULL OR page_count > 0),
            CONSTRAINT ck_document_extractions_completion CHECK (
                (extraction_status IN ('PENDING', 'PROCESSING') AND completed_at IS NULL)
                OR (extraction_status IN ('COMPLETED', 'FAILED') AND completed_at IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_document_extractions_document ON valuation.document_extractions(case_id, document_id, created_at DESC)"
    )

    op.execute(
        """
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
            CONSTRAINT uq_extracted_fields_extraction_field
                UNIQUE (extraction_id, field_name),
            CONSTRAINT ck_extracted_fields_form_code
                CHECK (form_code IN ('F01', 'F02', 'F03', 'F04')),
            CONSTRAINT ck_extracted_fields_name
                CHECK (length(btrim(field_name)) > 0),
            CONSTRAINT ck_extracted_fields_confidence
                CHECK (confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_extracted_fields_page
                CHECK (source_page IS NULL OR source_page > 0),
            CONSTRAINT ck_extracted_fields_status CHECK (
                field_status IN ('EXTRACTED', 'NEEDS_CONFIRMATION', 'CONFIRMED', 'REJECTED', 'APPLIED')
            ),
            CONSTRAINT ck_extracted_fields_confirmation CHECK (
                (field_status IN ('EXTRACTED', 'NEEDS_CONFIRMATION')
                    AND confirmed_value IS NULL
                    AND confirmed_by_user_id IS NULL
                    AND confirmed_at IS NULL
                    AND applied_form_instance_id IS NULL
                    AND applied_at IS NULL)
                OR (field_status = 'REJECTED'
                    AND confirmed_value IS NULL
                    AND confirmed_by_user_id IS NOT NULL
                    AND confirmed_at IS NOT NULL
                    AND applied_form_instance_id IS NULL
                    AND applied_at IS NULL)
                OR (field_status = 'CONFIRMED'
                    AND confirmed_value IS NOT NULL
                    AND confirmed_by_user_id IS NOT NULL
                    AND confirmed_at IS NOT NULL
                    AND applied_form_instance_id IS NULL
                    AND applied_at IS NULL)
                OR (field_status = 'APPLIED'
                    AND confirmed_value IS NOT NULL
                    AND confirmed_by_user_id IS NOT NULL
                    AND confirmed_at IS NOT NULL
                    AND applied_form_instance_id IS NOT NULL
                    AND applied_at IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_extracted_fields_case_status ON valuation.extracted_fields(case_id, form_code, field_status)"
    )
    op.execute(
        "CREATE TRIGGER trg_extracted_fields_updated_at BEFORE UPDATE ON valuation.extracted_fields FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at()"
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
            CONSTRAINT ck_assistant_sessions_form
                CHECK (selected_form_type = 'F03'),
            CONSTRAINT ck_assistant_sessions_json CHECK (
                jsonb_typeof(missing_fields) = 'array'
                AND jsonb_typeof(missing_documents) = 'array'
            ),
            CONSTRAINT ck_assistant_sessions_tool_status CHECK (
                last_tool_status IS NULL OR last_tool_status IN ('PENDING', 'SUCCESS', 'FAILED')
            ),
            CONSTRAINT ck_assistant_sessions_provider
                CHECK (provider IN ('MOCK', 'BEDROCK')),
            CONSTRAINT ck_assistant_sessions_status
                CHECK (session_status IN ('ACTIVE', 'COMPLETED', 'FAILED', 'ARCHIVED'))
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_assistant_sessions_case_user ON valuation.assistant_sessions(case_id, user_id, updated_at DESC)"
    )
    op.execute(
        "CREATE TRIGGER trg_assistant_sessions_updated_at BEFORE UPDATE ON valuation.assistant_sessions FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at()"
    )

    op.execute(
        """
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
            CONSTRAINT uq_assistant_messages_no
                UNIQUE (assistant_session_id, message_no),
            CONSTRAINT ck_assistant_messages_no CHECK (message_no > 0),
            CONSTRAINT ck_assistant_messages_role
                CHECK (role IN ('USER', 'ASSISTANT', 'TOOL')),
            CONSTRAINT ck_assistant_messages_content
                CHECK (length(btrim(content)) > 0),
            CONSTRAINT ck_assistant_messages_tool CHECK (
                (role = 'TOOL' AND tool_name IS NOT NULL)
                OR (role <> 'TOOL' AND tool_name IS NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_assistant_messages_session ON valuation.assistant_messages(assistant_session_id, message_no)"
    )

    op.execute(
        "COMMENT ON TABLE valuation.document_extractions IS '案件文件擷取工作；PDF 原檔仍只存 MinIO'"
    )
    op.execute(
        "COMMENT ON TABLE valuation.extracted_fields IS 'AI/OCR 候選欄位；確認前不可寫入正式表單'"
    )
    op.execute(
        "COMMENT ON TABLE valuation.assistant_sessions IS 'F03 AI 製作流程狀態；不保存模型思考過程'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE valuation.assistant_messages")
    op.execute("DROP TABLE valuation.assistant_sessions")
    op.execute("DROP TABLE valuation.extracted_fields")
    op.execute("DROP TABLE valuation.document_extractions")
