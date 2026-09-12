-- 003 法規知識模組：原始檔存 MinIO，文字、頁碼與向量存 PostgreSQL
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS knowledge;

CREATE TABLE knowledge.documents (
    document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_code varchar(80) NOT NULL,
    title varchar(300) NOT NULL,
    document_type varchar(30) NOT NULL,
    original_filename varchar(255) NOT NULL,
    mime_type varchar(100) NOT NULL DEFAULT 'application/pdf',
    bucket_name varchar(63) NOT NULL DEFAULT 'knowledge',
    object_key varchar(1024) NOT NULL,
    checksum_sha256 char(64) NOT NULL,
    file_size_bytes bigint,
    version_no integer NOT NULL DEFAULT 1,
    effective_from date,
    effective_to date,
    extraction_status varchar(20) NOT NULL DEFAULT 'PENDING',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_code, version_no),
    UNIQUE (bucket_name, object_key),
    CONSTRAINT ck_knowledge_document_type CHECK (document_type IN ('REGULATION', 'STANDARD', 'MANUAL', 'OTHER')),
    CONSTRAINT ck_knowledge_bucket CHECK (bucket_name = 'knowledge'),
    CONSTRAINT ck_knowledge_object_key CHECK (object_key !~ '^(https?://|/)' AND position('..' in object_key) = 0),
    CONSTRAINT ck_knowledge_checksum CHECK (checksum_sha256 ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT ck_knowledge_size CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    CONSTRAINT ck_knowledge_dates CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from),
    CONSTRAINT ck_knowledge_extraction CHECK (extraction_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'))
);

CREATE TABLE knowledge.chunks (
    chunk_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES knowledge.documents(document_id) ON DELETE CASCADE,
    chunk_no integer NOT NULL,
    content text NOT NULL,
    page_start integer,
    page_end integer,
    section_title varchar(300),
    article_no varchar(100),
    token_count integer,
    content_checksum_sha256 char(64) NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_no),
    CONSTRAINT ck_chunks_no CHECK (chunk_no > 0),
    CONSTRAINT ck_chunks_content CHECK (length(btrim(content)) > 0),
    CONSTRAINT ck_chunks_pages CHECK (
        (page_start IS NULL AND page_end IS NULL) OR
        (page_start > 0 AND page_end >= page_start)
    ),
    CONSTRAINT ck_chunks_checksum CHECK (content_checksum_sha256 ~ '^[0-9a-fA-F]{64}$')
);

CREATE TABLE knowledge.embeddings (
    embedding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id uuid NOT NULL REFERENCES knowledge.chunks(chunk_id) ON DELETE CASCADE,
    model_name varchar(200) NOT NULL,
    model_version varchar(100),
    embedding vector NOT NULL,
    embedded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (chunk_id, model_name, model_version)
);

CREATE TABLE knowledge.conversations (
    conversation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid REFERENCES valuation.cases(case_id) ON DELETE SET NULL,
    user_id uuid REFERENCES auth.users(user_id) ON DELETE SET NULL,
    title varchar(200),
    status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_conversations_status CHECK (status IN ('ACTIVE', 'CLOSED', 'ARCHIVED'))
);

CREATE TABLE knowledge.messages (
    message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES knowledge.conversations(conversation_id) ON DELETE CASCADE,
    message_no integer NOT NULL,
    role varchar(20) NOT NULL,
    content text NOT NULL,
    model_name varchar(200),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, message_no),
    CONSTRAINT ck_messages_no CHECK (message_no > 0),
    CONSTRAINT ck_messages_role CHECK (role IN ('SYSTEM', 'USER', 'ASSISTANT')),
    CONSTRAINT ck_messages_content CHECK (length(btrim(content)) > 0)
);

CREATE TABLE knowledge.message_sources (
    message_source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id uuid NOT NULL REFERENCES knowledge.messages(message_id) ON DELETE CASCADE,
    chunk_id uuid NOT NULL REFERENCES knowledge.chunks(chunk_id) ON DELETE RESTRICT,
    citation_order integer NOT NULL,
    similarity_score numeric(12,9),
    cited_text text,
    page_start integer,
    page_end integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (message_id, citation_order),
    UNIQUE (message_id, chunk_id),
    CONSTRAINT ck_message_sources_order CHECK (citation_order > 0),
    CONSTRAINT ck_message_sources_pages CHECK (
        (page_start IS NULL AND page_end IS NULL) OR
        (page_start > 0 AND page_end >= page_start)
    )
);

CREATE TRIGGER trg_knowledge_documents_updated_at BEFORE UPDATE ON knowledge.documents
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_knowledge_conversations_updated_at BEFORE UPDATE ON knowledge.conversations
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE INDEX idx_knowledge_documents_type ON knowledge.documents(document_type, effective_from DESC);
CREATE INDEX idx_knowledge_chunks_document ON knowledge.chunks(document_id, chunk_no);
CREATE INDEX idx_knowledge_messages_conversation ON knowledge.messages(conversation_id, message_no);
CREATE INDEX idx_knowledge_sources_chunk ON knowledge.message_sources(chunk_id);

COMMENT ON SCHEMA knowledge IS '法規原始文件、文字切片、向量、對話與引用來源';
COMMENT ON COLUMN knowledge.documents.object_key IS '僅保存 MinIO object key，不保存 endpoint 或簽章 URL';

COMMIT;
