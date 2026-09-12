-- 002 選配模組：土地市價查估輔助系統 - RAG Schema v1
-- 適用：PostgreSQL 15+、pgvector
-- 前置條件：已執行核心schema.sql並存在valuation Schema。
-- 不做RAG時請勿執行本檔；核心估價流程不依賴本Schema。
-- 依賴方向：rag.* 可以引用 valuation.*，valuation.* 不引用 rag.*。

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.schemata
        WHERE schema_name = 'valuation'
    ) THEN
        RAISE EXCEPTION 'Required core schema valuation does not exist. Run schema.sql first.';
    END IF;
END;
$$;

CREATE SCHEMA IF NOT EXISTS rag;
SET search_path TO rag, valuation, public;

-- ============================================================
-- 共用函式
-- ============================================================

CREATE OR REPLACE FUNCTION rag.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION rag.validate_embedding_dimension()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    expected_dimension integer;
BEGIN
    SELECT vector_dimension
    INTO expected_dimension
    FROM rag.embedding_models
    WHERE embedding_model_id = NEW.embedding_model_id;

    IF expected_dimension IS NULL THEN
        RAISE EXCEPTION 'Embedding model % does not exist', NEW.embedding_model_id;
    END IF;

    IF vector_dims(NEW.embedding) <> expected_dimension THEN
        RAISE EXCEPTION
            'Embedding dimension % does not match model dimension %',
            vector_dims(NEW.embedding), expected_dimension;
    END IF;

    RETURN NEW;
END;
$$;

-- ============================================================
-- 1. 知識文件與切片
-- ============================================================

CREATE TABLE knowledge_documents (
    knowledge_document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_code varchar(80) NOT NULL,
    document_title varchar(300) NOT NULL,
    document_type varchar(40) NOT NULL,
    version_no integer NOT NULL DEFAULT 1,
    effective_from date,
    effective_to date,
    bucket_name varchar(63) NOT NULL DEFAULT 'knowledge',
    object_key varchar(1024) NOT NULL,
    checksum_sha256 char(64) NOT NULL,
    mime_type varchar(100),
    language_code varchar(20) NOT NULL DEFAULT 'zh-TW',
    confidentiality_level varchar(20) NOT NULL DEFAULT 'INTERNAL',
    extraction_status varchar(20) NOT NULL DEFAULT 'PENDING',
    document_status varchar(20) NOT NULL DEFAULT 'DRAFT',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_knowledge_documents_code_version UNIQUE (document_code, version_no),
    CONSTRAINT uq_knowledge_documents_object UNIQUE (bucket_name, object_key),
    CONSTRAINT uq_knowledge_documents_checksum UNIQUE (checksum_sha256),
    CONSTRAINT ck_knowledge_documents_version CHECK (version_no > 0),
    CONSTRAINT ck_knowledge_documents_bucket CHECK (bucket_name = 'knowledge'),
    CONSTRAINT ck_knowledge_documents_object_key CHECK (
        object_key !~ '^(https?://|/)' AND position('..' in object_key) = 0
    ),
    CONSTRAINT ck_knowledge_documents_dates CHECK (
        effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from
    ),
    CONSTRAINT ck_knowledge_documents_sha256 CHECK (
        checksum_sha256 ~ '^[0-9a-fA-F]{64}$'
    ),
    CONSTRAINT ck_knowledge_documents_type CHECK (
        document_type IN (
            'LAW', 'REGULATION', 'VALUATION_STANDARD', 'MANUAL',
            'FORM_GUIDE', 'FAQ', 'SYSTEM_GUIDE', 'OTHER'
        )
    ),
    CONSTRAINT ck_knowledge_documents_confidentiality CHECK (
        confidentiality_level IN ('PUBLIC', 'INTERNAL', 'SENSITIVE', 'RESTRICTED')
    ),
    CONSTRAINT ck_knowledge_documents_extraction CHECK (
        extraction_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')
    ),
    CONSTRAINT ck_knowledge_documents_status CHECK (
        document_status IN ('DRAFT', 'PUBLISHED', 'RETIRED')
    )
);

CREATE TABLE knowledge_chunks (
    chunk_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_document_id uuid NOT NULL,
    chunk_no integer NOT NULL,
    content text NOT NULL,
    page_start integer,
    page_end integer,
    section_title varchar(300),
    article_no varchar(100),
    token_count integer,
    content_checksum_sha256 char(64) NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_knowledge_chunks_document
        FOREIGN KEY (knowledge_document_id)
        REFERENCES knowledge_documents(knowledge_document_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT uq_knowledge_chunks_document_no UNIQUE (knowledge_document_id, chunk_no),
    CONSTRAINT uq_knowledge_chunks_document_checksum
        UNIQUE (knowledge_document_id, content_checksum_sha256),
    CONSTRAINT ck_knowledge_chunks_no CHECK (chunk_no > 0),
    CONSTRAINT ck_knowledge_chunks_content CHECK (length(btrim(content)) > 0),
    CONSTRAINT ck_knowledge_chunks_pages CHECK (
        (page_start IS NULL AND page_end IS NULL)
        OR (
            page_start IS NOT NULL
            AND page_end IS NOT NULL
            AND page_start > 0
            AND page_end >= page_start
        )
    ),
    CONSTRAINT ck_knowledge_chunks_tokens CHECK (token_count IS NULL OR token_count > 0),
    CONSTRAINT ck_knowledge_chunks_sha256 CHECK (
        content_checksum_sha256 ~ '^[0-9a-fA-F]{64}$'
    )
);

-- 將知識文件連結到核心規則版本。
-- 關聯放在rag側，因此刪除整個rag Schema不影響核心資料表。
CREATE TABLE knowledge_rule_links (
    knowledge_rule_link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_document_id uuid NOT NULL,
    rule_version_id uuid NOT NULL,
    source_section varchar(300),
    page_start integer,
    page_end integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_knowledge_rule_links_document
        FOREIGN KEY (knowledge_document_id)
        REFERENCES knowledge_documents(knowledge_document_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_rule_links_rule_version
        FOREIGN KEY (rule_version_id)
        REFERENCES valuation.rule_versions(rule_version_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_knowledge_rule_links_pair
        UNIQUE NULLS NOT DISTINCT (knowledge_document_id, rule_version_id, source_section),
    CONSTRAINT ck_knowledge_rule_links_pages CHECK (
        (page_start IS NULL AND page_end IS NULL)
        OR (
            page_start IS NOT NULL
            AND page_end IS NOT NULL
            AND page_start > 0
            AND page_end >= page_start
        )
    )
);

-- ============================================================
-- 2. Embedding模型與向量
-- ============================================================

CREATE TABLE embedding_models (
    embedding_model_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_code varchar(100) NOT NULL,
    model_name varchar(200) NOT NULL,
    model_version varchar(100),
    provider varchar(100),
    vector_dimension integer NOT NULL,
    distance_metric varchar(20) NOT NULL DEFAULT 'COSINE',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_embedding_models_code UNIQUE (model_code),
    CONSTRAINT ck_embedding_models_dimension CHECK (vector_dimension > 0),
    CONSTRAINT ck_embedding_models_metric CHECK (
        distance_metric IN ('COSINE', 'L2', 'INNER_PRODUCT')
    )
);

CREATE TABLE knowledge_embeddings (
    embedding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id uuid NOT NULL,
    embedding_model_id uuid NOT NULL,
    embedding vector NOT NULL,
    content_checksum_sha256 char(64) NOT NULL,
    embedded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_knowledge_embeddings_chunk
        FOREIGN KEY (chunk_id) REFERENCES knowledge_chunks(chunk_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_embeddings_model
        FOREIGN KEY (embedding_model_id) REFERENCES embedding_models(embedding_model_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_knowledge_embeddings_chunk_model UNIQUE (chunk_id, embedding_model_id),
    CONSTRAINT ck_knowledge_embeddings_sha256 CHECK (
        content_checksum_sha256 ~ '^[0-9a-fA-F]{64}$'
    )
);

-- 初期不建立HNSW／IVFFlat，避免尚未選定模型時鎖死向量維度。
-- 模型與維度確定後，再建立指定維度的部分索引。例如：
-- CREATE INDEX idx_embeddings_model_hnsw
-- ON rag.knowledge_embeddings
-- USING hnsw ((embedding::vector(768)) vector_cosine_ops)
-- WHERE embedding_model_id = '<已確定的模型UUID>'::uuid;

-- ============================================================
-- 3. 對話、檢索與引用
-- ============================================================

CREATE TABLE rag_sessions (
    rag_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid,
    user_id uuid,
    session_title varchar(200),
    session_status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    CONSTRAINT fk_rag_sessions_case
        FOREIGN KEY (case_id) REFERENCES valuation.cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_rag_sessions_status CHECK (
        session_status IN ('ACTIVE', 'CLOSED', 'ARCHIVED')
    ),
    CONSTRAINT ck_rag_sessions_time CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE TABLE rag_messages (
    rag_message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rag_session_id uuid NOT NULL,
    message_no integer NOT NULL,
    message_role varchar(20) NOT NULL,
    content text NOT NULL,
    answer_status varchar(20),
    generation_model varchar(200),
    prompt_version varchar(100),
    confidence_score numeric(6,5),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_rag_messages_session
        FOREIGN KEY (rag_session_id) REFERENCES rag_sessions(rag_session_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT uq_rag_messages_session_no UNIQUE (rag_session_id, message_no),
    CONSTRAINT ck_rag_messages_no CHECK (message_no > 0),
    CONSTRAINT ck_rag_messages_role CHECK (
        message_role IN ('SYSTEM', 'USER', 'ASSISTANT')
    ),
    CONSTRAINT ck_rag_messages_content CHECK (length(btrim(content)) > 0),
    CONSTRAINT ck_rag_messages_status CHECK (
        answer_status IS NULL OR answer_status IN ('ANSWERED', 'NO_ANSWER', 'FAILED', 'BLOCKED')
    ),
    CONSTRAINT ck_rag_messages_confidence CHECK (
        confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1
    )
);

CREATE TABLE rag_retrievals (
    retrieval_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rag_message_id uuid NOT NULL,
    chunk_id uuid NOT NULL,
    retrieval_rank integer NOT NULL,
    similarity_score numeric(12,9),
    rerank_score numeric(12,9),
    was_cited boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_rag_retrievals_message
        FOREIGN KEY (rag_message_id) REFERENCES rag_messages(rag_message_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_rag_retrievals_chunk
        FOREIGN KEY (chunk_id) REFERENCES knowledge_chunks(chunk_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_rag_retrievals_message_chunk UNIQUE (rag_message_id, chunk_id),
    CONSTRAINT uq_rag_retrievals_message_rank UNIQUE (rag_message_id, retrieval_rank),
    CONSTRAINT ck_rag_retrievals_rank CHECK (retrieval_rank > 0)
);

CREATE TABLE rag_citations (
    citation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rag_message_id uuid NOT NULL,
    chunk_id uuid NOT NULL,
    citation_order integer NOT NULL,
    cited_text text,
    source_locator varchar(500) NOT NULL,
    page_start integer,
    page_end integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_rag_citations_message
        FOREIGN KEY (rag_message_id) REFERENCES rag_messages(rag_message_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_rag_citations_chunk
        FOREIGN KEY (chunk_id) REFERENCES knowledge_chunks(chunk_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_rag_citations_message_order UNIQUE (rag_message_id, citation_order),
    CONSTRAINT ck_rag_citations_order CHECK (citation_order > 0),
    CONSTRAINT ck_rag_citations_pages CHECK (
        (page_start IS NULL AND page_end IS NULL)
        OR (
            page_start IS NOT NULL
            AND page_end IS NOT NULL
            AND page_start > 0
            AND page_end >= page_start
        )
    )
);

CREATE TABLE rag_feedback (
    feedback_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rag_message_id uuid NOT NULL,
    user_id uuid,
    feedback_type varchar(30) NOT NULL,
    feedback_reason text,
    corrected_answer text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_rag_feedback_message
        FOREIGN KEY (rag_message_id) REFERENCES rag_messages(rag_message_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT uq_rag_feedback_message_user UNIQUE NULLS NOT DISTINCT (rag_message_id, user_id),
    CONSTRAINT ck_rag_feedback_type CHECK (
        feedback_type IN ('HELPFUL', 'NOT_HELPFUL', 'WRONG_SOURCE', 'OUTDATED', 'NO_ANSWER')
    )
);

-- ============================================================
-- 4. 與核心檢核結果的選配連結
-- ============================================================

CREATE TABLE finding_explanations (
    finding_explanation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id uuid NOT NULL,
    rag_message_id uuid NOT NULL,
    explanation_snapshot text NOT NULL,
    citation_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    generated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_finding_explanations_finding
        FOREIGN KEY (finding_id) REFERENCES valuation.validation_findings(finding_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_finding_explanations_message
        FOREIGN KEY (rag_message_id) REFERENCES rag_messages(rag_message_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_finding_explanations_message UNIQUE (finding_id, rag_message_id),
    CONSTRAINT ck_finding_explanations_content CHECK (
        length(btrim(explanation_snapshot)) > 0
    )
);

CREATE TABLE chunk_validation_rule_links (
    chunk_validation_rule_link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id uuid NOT NULL,
    validation_rule_id uuid NOT NULL,
    link_type varchar(20) NOT NULL DEFAULT 'SUPPORTS',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_chunk_validation_rule_links_chunk
        FOREIGN KEY (chunk_id) REFERENCES knowledge_chunks(chunk_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_chunk_validation_rule_links_rule
        FOREIGN KEY (validation_rule_id)
        REFERENCES valuation.validation_rules(validation_rule_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_chunk_validation_rule_links_pair UNIQUE (chunk_id, validation_rule_id),
    CONSTRAINT ck_chunk_validation_rule_links_type CHECK (
        link_type IN ('SUPPORTS', 'EXPLAINS', 'SUPERSEDES')
    )
);

-- ============================================================
-- 5. Trigger與索引
-- ============================================================

CREATE TRIGGER trg_knowledge_documents_updated_at
BEFORE UPDATE ON knowledge_documents
FOR EACH ROW EXECUTE FUNCTION rag.set_updated_at();

CREATE TRIGGER trg_knowledge_embeddings_dimension
BEFORE INSERT OR UPDATE OF embedding, embedding_model_id ON knowledge_embeddings
FOR EACH ROW EXECUTE FUNCTION rag.validate_embedding_dimension();

CREATE INDEX idx_knowledge_documents_type_status
    ON knowledge_documents(document_type, document_status, effective_from DESC);

CREATE INDEX idx_knowledge_documents_published
    ON knowledge_documents(effective_from DESC, effective_to)
    WHERE document_status = 'PUBLISHED';

CREATE INDEX idx_knowledge_chunks_document_active
    ON knowledge_chunks(knowledge_document_id, chunk_no)
    WHERE is_active;

CREATE INDEX idx_knowledge_chunks_section
    ON knowledge_chunks(knowledge_document_id, section_title, article_no);

CREATE INDEX idx_knowledge_chunks_metadata_gin
    ON knowledge_chunks USING gin(metadata);

CREATE INDEX idx_knowledge_rule_links_rule
    ON knowledge_rule_links(rule_version_id);

CREATE INDEX idx_knowledge_embeddings_chunk
    ON knowledge_embeddings(chunk_id);

CREATE INDEX idx_knowledge_embeddings_model
    ON knowledge_embeddings(embedding_model_id);

CREATE INDEX idx_rag_sessions_case_time
    ON rag_sessions(case_id, started_at DESC)
    WHERE case_id IS NOT NULL;

CREATE INDEX idx_rag_sessions_user_time
    ON rag_sessions(user_id, started_at DESC)
    WHERE user_id IS NOT NULL;

CREATE INDEX idx_rag_messages_session_time
    ON rag_messages(rag_session_id, message_no);

CREATE INDEX idx_rag_retrievals_message_rank
    ON rag_retrievals(rag_message_id, retrieval_rank);

CREATE INDEX idx_rag_retrievals_chunk
    ON rag_retrievals(chunk_id);

CREATE INDEX idx_rag_citations_message_order
    ON rag_citations(rag_message_id, citation_order);

CREATE INDEX idx_rag_citations_chunk
    ON rag_citations(chunk_id);

CREATE INDEX idx_rag_feedback_message
    ON rag_feedback(rag_message_id);

CREATE INDEX idx_finding_explanations_finding
    ON finding_explanations(finding_id, generated_at DESC);

CREATE INDEX idx_chunk_validation_rule_links_rule
    ON chunk_validation_rule_links(validation_rule_id);

-- ============================================================
-- 6. 說明
-- ============================================================

COMMENT ON SCHEMA rag IS '選配RAG知識問答模組；刪除或未建立本Schema不影響valuation核心估價流程';
COMMENT ON TABLE knowledge_documents IS '法規、評價基準、手冊、表單規範及FAQ原始文件Metadata';
COMMENT ON TABLE knowledge_chunks IS '知識文件切片及可追溯頁碼、章節與條文資訊';
COMMENT ON TABLE embedding_models IS 'Embedding模型、版本、維度及距離計算方式';
COMMENT ON TABLE knowledge_embeddings IS '知識切片向量；初期使用無固定維度vector以延後模型決策';
COMMENT ON TABLE rag_sessions IS '一次知識問答對話，可選擇連結特定估價案件';
COMMENT ON TABLE rag_messages IS '使用者問題、系統訊息與RAG回答';
COMMENT ON TABLE rag_retrievals IS '每次回答實際檢索到的知識切片、排名及分數';
COMMENT ON TABLE rag_citations IS '回答顯示的來源、頁碼與引用順序';
COMMENT ON TABLE rag_feedback IS '使用者對RAG回答的評價與更正內容';
COMMENT ON TABLE finding_explanations IS 'RAG對核心檢核疑點產生的解釋與引用快照';

COMMIT;
