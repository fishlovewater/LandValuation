"""Harden documents, review evidence, audit and knowledge governance.

Revision ID: 20260824_0004
Revises: 20260823_0003
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260824_0004"
down_revision: Union[str, Sequence[str], None] = "20260823_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A physical object is one version; document_group_id identifies the logical document.
    op.execute("ALTER TABLE valuation.documents ADD COLUMN document_group_id uuid")
    op.execute("UPDATE valuation.documents SET document_group_id = document_id")
    op.execute(
        "ALTER TABLE valuation.documents ALTER COLUMN document_group_id SET DEFAULT gen_random_uuid()"
    )
    op.execute("ALTER TABLE valuation.documents ALTER COLUMN document_group_id SET NOT NULL")
    op.execute("ALTER TABLE valuation.documents ADD COLUMN storage_etag varchar(255)")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM valuation.documents
                WHERE mime_type IS NULL OR file_size_bytes IS NULL
            ) THEN
                RAISE EXCEPTION
                    'valuation.documents contains NULL mime_type/file_size_bytes; repair metadata before upgrade';
            END IF;
        END
        $$
        """
    )
    op.execute("ALTER TABLE valuation.documents ALTER COLUMN mime_type SET NOT NULL")
    op.execute("ALTER TABLE valuation.documents ALTER COLUMN file_size_bytes SET NOT NULL")
    op.execute(
        """
        ALTER TABLE valuation.documents
        ADD CONSTRAINT uq_documents_group_version
        UNIQUE (case_id, document_group_id, version_no)
        """
    )
    op.execute(
        "CREATE INDEX idx_documents_group_active ON valuation.documents(case_id, document_group_id, version_no DESC) WHERE is_active"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.documents.document_group_id IS '同一份邏輯文件的穩定 UUID；document_id 識別單一實體版本'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.documents.storage_etag IS 'MinIO 物件 ETag；用於快速核對，不取代 SHA-256'"
    )

    # Link a rule version to its governed source document.
    op.execute("ALTER TABLE valuation.rule_versions ADD COLUMN source_document_id uuid")
    op.execute(
        """
        ALTER TABLE valuation.rule_versions
        ADD CONSTRAINT fk_rule_versions_source_document
        FOREIGN KEY (source_document_id) REFERENCES knowledge.documents(document_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
        """
    )
    op.execute(
        "CREATE INDEX idx_rule_versions_source_document ON valuation.rule_versions(source_document_id) WHERE source_document_id IS NOT NULL"
    )

    # A run must identify a rule version or preserve the actual ruleset snapshot.
    op.execute("ALTER TABLE valuation.validation_runs ADD COLUMN rule_version_id uuid")
    op.execute("ALTER TABLE valuation.validation_runs ADD COLUMN ruleset_snapshot jsonb")
    op.execute(
        """
        ALTER TABLE valuation.validation_runs
        ADD CONSTRAINT fk_validation_runs_rule_version
        FOREIGN KEY (rule_version_id) REFERENCES valuation.rule_versions(rule_version_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
        """
    )
    op.execute(
        """
        ALTER TABLE valuation.validation_runs
        ADD CONSTRAINT ck_validation_runs_ruleset_traceable CHECK (
            rule_version_id IS NOT NULL
            OR (ruleset_snapshot IS NOT NULL AND ruleset_snapshot <> '{}'::jsonb)
        )
        """
    )

    # Machine findings are immutable evidence. Human state and decisions live in review.*.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM valuation.validation_findings
                WHERE manual_decision IS NOT NULL
                   OR decision_reason IS NOT NULL
                   OR decided_by_user_id IS NOT NULL
                   OR decided_at IS NOT NULL
                   OR handling_status <> 'OPEN'
            ) THEN
                RAISE EXCEPTION
                    'validation_findings contains human decision data; migrate it to review.decisions before upgrade';
            END IF;
        END
        $$
        """
    )
    op.execute("DROP INDEX IF EXISTS valuation.idx_validation_findings_open")
    op.execute("DROP INDEX IF EXISTS valuation.idx_validation_findings_run_status")
    op.execute(
        "ALTER TABLE valuation.validation_findings DROP CONSTRAINT fk_validation_findings_decided_by_user"
    )
    op.execute(
        "ALTER TABLE valuation.validation_findings DROP CONSTRAINT ck_validation_findings_decision_reason"
    )
    op.execute(
        "ALTER TABLE valuation.validation_findings DROP CONSTRAINT ck_validation_findings_decision"
    )
    op.execute(
        "ALTER TABLE valuation.validation_findings DROP CONSTRAINT ck_validation_findings_status"
    )
    op.execute(
        """
        ALTER TABLE valuation.validation_findings
        DROP COLUMN handling_status,
        DROP COLUMN manual_decision,
        DROP COLUMN decision_reason,
        DROP COLUMN decided_by_user_id,
        DROP COLUMN decided_at
        """
    )
    op.execute(
        "CREATE INDEX idx_validation_findings_run_severity ON valuation.validation_findings(validation_run_id, severity)"
    )
    op.execute(
        "COMMENT ON TABLE valuation.validation_findings IS '不可變的機器檢核證據；人工處理狀態及決策分別以 review.findings 與 review.decisions 為準'"
    )

    # Deleting a finding must never erase its audit decision.
    op.execute(
        "ALTER TABLE review.decisions DROP CONSTRAINT decisions_finding_id_fkey"
    )
    op.execute(
        """
        ALTER TABLE review.decisions
        ADD CONSTRAINT fk_decisions_finding
        FOREIGN KEY (finding_id) REFERENCES review.findings(finding_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
        """
    )

    # Track who resolved or waived a missing item.
    op.execute("ALTER TABLE review.missing_items ADD COLUMN resolved_by_user_id uuid")
    op.execute(
        """
        ALTER TABLE review.missing_items
        ADD CONSTRAINT fk_missing_items_resolved_by_user
        FOREIGN KEY (resolved_by_user_id) REFERENCES auth.users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
        """
    )
    op.execute(
        """
        ALTER TABLE review.missing_items
        ADD CONSTRAINT ck_missing_items_resolution_audit CHECK (
            (status = 'OPEN' AND resolved_by_user_id IS NULL AND resolved_at IS NULL)
            OR
            (status IN ('RESOLVED', 'WAIVED') AND resolved_by_user_id IS NOT NULL AND resolved_at IS NOT NULL)
        )
        """
    )

    # Correlate database access audit records with FastAPI logs.
    op.execute("ALTER TABLE history.access_logs ADD COLUMN request_id uuid")
    op.execute(
        "ALTER TABLE history.access_logs ADD COLUMN result varchar(20) NOT NULL DEFAULT 'SUCCESS'"
    )
    op.execute(
        """
        ALTER TABLE history.access_logs
        ADD CONSTRAINT ck_access_logs_result CHECK (result IN ('SUCCESS', 'DENIED', 'FAILED'))
        """
    )
    op.execute(
        "CREATE INDEX idx_access_logs_request_id ON history.access_logs(request_id) WHERE request_id IS NOT NULL"
    )

    # Extraction and publication are separate lifecycle dimensions.
    op.execute(
        "ALTER TABLE knowledge.documents ADD COLUMN publication_status varchar(20) NOT NULL DEFAULT 'DRAFT'"
    )
    op.execute("ALTER TABLE knowledge.documents ADD COLUMN approved_by_user_id uuid")
    op.execute("ALTER TABLE knowledge.documents ADD COLUMN approved_at timestamptz")
    op.execute(
        """
        ALTER TABLE knowledge.documents
        ADD CONSTRAINT fk_knowledge_documents_approved_by_user
        FOREIGN KEY (approved_by_user_id) REFERENCES auth.users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge.documents
        ADD CONSTRAINT ck_knowledge_publication_status CHECK (
            publication_status IN ('DRAFT', 'PUBLISHED', 'DISABLED', 'ARCHIVED')
        )
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge.documents
        ADD CONSTRAINT ck_knowledge_publication_approval CHECK (
            publication_status <> 'PUBLISHED'
            OR (approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_knowledge_documents_publication ON knowledge.documents(publication_status, extraction_status, document_type)"
    )

    # Record the model version attached to an answer citation.
    op.execute("ALTER TABLE knowledge.message_sources ADD COLUMN model_version varchar(100)")
    op.execute(
        "COMMENT ON COLUMN knowledge.message_sources.model_version IS '產生此引用排名或檢索結果的模型版本'"
    )

    # Keep legacy rate column names stable, but make their semantics explicit.
    op.execute(
        "COMMENT ON COLUMN valuation.transaction_financing.own_funds_rate IS '自有資金利率（interest rate）；不是資金占比'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.transaction_financing.borrowed_funds_rate IS '借入資金利率（interest rate）；不是資金占比'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.transaction_financing.presale_income_rate IS '預售收入資金利率（interest rate）；不是資金占比'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.transaction_financing.own_funds_ratio IS '自有資金占總資金的比例'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.transaction_financing.borrowed_funds_ratio IS '借入資金占總資金的比例'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.transaction_financing.presale_income_ratio IS '預售收入占總資金的比例'"
    )

    op.execute(
        """
        COMMENT ON TABLE valuation.valuations IS
        '保留的統一估價摘要表；黑客鬆階段暫不讀寫。F03 以 benchmark_valuations，F04 以 parcel_valuations/parcel_valuation_items 為權威來源'
        """
    )


def downgrade() -> None:
    op.execute(
        "COMMENT ON TABLE valuation.valuations IS '對外統一的估價計算結果摘要'"
    )
    for column in (
        "own_funds_rate",
        "borrowed_funds_rate",
        "presale_income_rate",
        "own_funds_ratio",
        "borrowed_funds_ratio",
        "presale_income_ratio",
    ):
        op.execute(f"COMMENT ON COLUMN valuation.transaction_financing.{column} IS NULL")

    op.execute("ALTER TABLE knowledge.message_sources DROP COLUMN model_version")
    op.execute("DROP INDEX IF EXISTS knowledge.idx_knowledge_documents_publication")
    op.execute(
        "ALTER TABLE knowledge.documents DROP CONSTRAINT ck_knowledge_publication_approval"
    )
    op.execute(
        "ALTER TABLE knowledge.documents DROP CONSTRAINT ck_knowledge_publication_status"
    )
    op.execute(
        "ALTER TABLE knowledge.documents DROP CONSTRAINT fk_knowledge_documents_approved_by_user"
    )
    op.execute(
        """
        ALTER TABLE knowledge.documents
        DROP COLUMN approved_at,
        DROP COLUMN approved_by_user_id,
        DROP COLUMN publication_status
        """
    )

    op.execute("DROP INDEX IF EXISTS history.idx_access_logs_request_id")
    op.execute("ALTER TABLE history.access_logs DROP CONSTRAINT ck_access_logs_result")
    op.execute("ALTER TABLE history.access_logs DROP COLUMN result, DROP COLUMN request_id")

    op.execute(
        "ALTER TABLE review.missing_items DROP CONSTRAINT ck_missing_items_resolution_audit"
    )
    op.execute(
        "ALTER TABLE review.missing_items DROP CONSTRAINT fk_missing_items_resolved_by_user"
    )
    op.execute("ALTER TABLE review.missing_items DROP COLUMN resolved_by_user_id")

    op.execute("ALTER TABLE review.decisions DROP CONSTRAINT fk_decisions_finding")
    op.execute(
        """
        ALTER TABLE review.decisions
        ADD CONSTRAINT decisions_finding_id_fkey
        FOREIGN KEY (finding_id) REFERENCES review.findings(finding_id)
        ON DELETE CASCADE
        """
    )

    op.execute("DROP INDEX IF EXISTS valuation.idx_validation_findings_run_severity")
    op.execute(
        """
        ALTER TABLE valuation.validation_findings
        ADD COLUMN handling_status varchar(20) NOT NULL DEFAULT 'OPEN',
        ADD COLUMN manual_decision varchar(20),
        ADD COLUMN decision_reason text,
        ADD COLUMN decided_by_user_id uuid,
        ADD COLUMN decided_at timestamptz
        """
    )
    op.execute(
        """
        ALTER TABLE valuation.validation_findings
        ADD CONSTRAINT ck_validation_findings_status CHECK (
            handling_status IN ('OPEN', 'ACCEPTED', 'REJECTED', 'CORRECTED', 'IGNORED')
        ),
        ADD CONSTRAINT ck_validation_findings_decision CHECK (
            manual_decision IS NULL OR manual_decision IN ('ACCEPT_AI', 'REJECT_AI', 'MODIFY')
        ),
        ADD CONSTRAINT ck_validation_findings_decision_reason CHECK (
            manual_decision IS NULL OR manual_decision = 'ACCEPT_AI'
            OR nullif(btrim(decision_reason), '') IS NOT NULL
        ),
        ADD CONSTRAINT fk_validation_findings_decided_by_user
            FOREIGN KEY (decided_by_user_id) REFERENCES auth.users(user_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
        """
    )
    op.execute(
        "CREATE INDEX idx_validation_findings_run_status ON valuation.validation_findings(validation_run_id, handling_status, severity)"
    )
    op.execute(
        "CREATE INDEX idx_validation_findings_open ON valuation.validation_findings(severity, finding_id) WHERE handling_status = 'OPEN'"
    )

    op.execute(
        "ALTER TABLE valuation.validation_runs DROP CONSTRAINT ck_validation_runs_ruleset_traceable"
    )
    op.execute(
        "ALTER TABLE valuation.validation_runs DROP CONSTRAINT fk_validation_runs_rule_version"
    )
    op.execute(
        "ALTER TABLE valuation.validation_runs DROP COLUMN ruleset_snapshot, DROP COLUMN rule_version_id"
    )

    op.execute("DROP INDEX IF EXISTS valuation.idx_rule_versions_source_document")
    op.execute(
        "ALTER TABLE valuation.rule_versions DROP CONSTRAINT fk_rule_versions_source_document"
    )
    op.execute("ALTER TABLE valuation.rule_versions DROP COLUMN source_document_id")

    op.execute("DROP INDEX IF EXISTS valuation.idx_documents_group_active")
    op.execute("ALTER TABLE valuation.documents DROP CONSTRAINT uq_documents_group_version")
    op.execute("ALTER TABLE valuation.documents ALTER COLUMN file_size_bytes DROP NOT NULL")
    op.execute("ALTER TABLE valuation.documents ALTER COLUMN mime_type DROP NOT NULL")
    op.execute(
        "ALTER TABLE valuation.documents DROP COLUMN storage_etag, DROP COLUMN document_group_id"
    )
