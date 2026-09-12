-- 002 平台核心模組：權限、審查、履歷與通用估價結果
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS review;
CREATE SCHEMA IF NOT EXISTS history;

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- auth
CREATE TABLE auth.users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username varchar(100) NOT NULL UNIQUE,
    email varchar(320) NOT NULL UNIQUE,
    password_hash text NOT NULL,
    display_name varchar(200) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_users_username CHECK (length(btrim(username)) > 0),
    CONSTRAINT ck_users_email CHECK (position('@' in email) > 1)
);

CREATE TABLE auth.roles (
    role_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_code varchar(80) NOT NULL UNIQUE,
    role_name varchar(150) NOT NULL,
    description text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auth.permissions (
    permission_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    permission_code varchar(120) NOT NULL UNIQUE,
    permission_name varchar(200) NOT NULL,
    resource varchar(100) NOT NULL,
    action varchar(50) NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_permissions_resource_action UNIQUE (resource, action)
);

CREATE TABLE auth.user_roles (
    user_id uuid NOT NULL REFERENCES auth.users(user_id) ON DELETE CASCADE,
    role_id uuid NOT NULL REFERENCES auth.roles(role_id) ON DELETE CASCADE,
    assigned_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE SET NULL,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE auth.role_permissions (
    role_id uuid NOT NULL REFERENCES auth.roles(role_id) ON DELETE CASCADE,
    permission_id uuid NOT NULL REFERENCES auth.permissions(permission_id) ON DELETE CASCADE,
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_roles_updated_at BEFORE UPDATE ON auth.roles
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- valuation: 對外統一的計算結果，現有 F03/F04 明細表仍保留。
CREATE TABLE valuation.valuations (
    valuation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL REFERENCES valuation.cases(case_id) ON DELETE RESTRICT,
    parcel_id uuid REFERENCES valuation.parcels(parcel_id) ON DELETE RESTRICT,
    form_instance_id uuid REFERENCES valuation.form_instances(form_instance_id) ON DELETE RESTRICT,
    valuation_type varchar(30) NOT NULL,
    unit_price numeric(20,2),
    total_value numeric(20,2),
    currency_code char(3) NOT NULL DEFAULT 'TWD',
    calculation_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_status varchar(20) NOT NULL DEFAULT 'DRAFT',
    calculated_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE SET NULL,
    calculated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_valuations_type CHECK (valuation_type IN ('BENCHMARK', 'PARCEL', 'CASE', 'OTHER')),
    CONSTRAINT ck_valuations_amount CHECK (
        (unit_price IS NULL OR unit_price >= 0) AND (total_value IS NULL OR total_value >= 0)
    ),
    CONSTRAINT ck_valuations_status CHECK (result_status IN ('DRAFT', 'CALCULATED', 'FINAL', 'VOID'))
);

CREATE TRIGGER trg_valuations_updated_at BEFORE UPDATE ON valuation.valuations
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE INDEX idx_valuations_case ON valuation.valuations(case_id, calculated_at DESC);

-- review
CREATE TABLE review.reviews (
    review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL REFERENCES valuation.cases(case_id) ON DELETE RESTRICT,
    form_instance_id uuid REFERENCES valuation.form_instances(form_instance_id) ON DELETE RESTRICT,
    validation_run_id uuid REFERENCES valuation.validation_runs(validation_run_id) ON DELETE SET NULL,
    review_type varchar(30) NOT NULL DEFAULT 'SMART_REVIEW',
    review_status varchar(20) NOT NULL DEFAULT 'PENDING',
    started_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE SET NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CONSTRAINT ck_reviews_type CHECK (review_type IN ('SMART_REVIEW', 'MANUAL_REVIEW', 'RECHECK')),
    CONSTRAINT ck_reviews_status CHECK (review_status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    CONSTRAINT ck_reviews_time CHECK (completed_at IS NULL OR completed_at >= started_at)
);

CREATE TABLE review.missing_items (
    missing_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id uuid NOT NULL REFERENCES review.reviews(review_id) ON DELETE CASCADE,
    item_code varchar(100) NOT NULL,
    item_name varchar(200) NOT NULL,
    document_type varchar(50),
    severity varchar(20) NOT NULL DEFAULT 'MEDIUM',
    status varchar(20) NOT NULL DEFAULT 'OPEN',
    details text,
    resolved_document_id uuid REFERENCES valuation.documents(document_id) ON DELETE SET NULL,
    resolved_at timestamptz,
    UNIQUE (review_id, item_code),
    CONSTRAINT ck_missing_items_severity CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT ck_missing_items_status CHECK (status IN ('OPEN', 'RESOLVED', 'WAIVED'))
);

CREATE TABLE review.findings (
    finding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id uuid NOT NULL REFERENCES review.reviews(review_id) ON DELETE CASCADE,
    source_validation_finding_id uuid REFERENCES valuation.validation_findings(finding_id) ON DELETE SET NULL,
    finding_code varchar(100) NOT NULL,
    finding_type varchar(50) NOT NULL,
    severity varchar(20) NOT NULL,
    title varchar(300) NOT NULL,
    description text NOT NULL,
    entity_type varchar(100),
    entity_id uuid,
    status varchar(20) NOT NULL DEFAULT 'OPEN',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (review_id, finding_code),
    CONSTRAINT ck_findings_severity CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT ck_findings_status CHECK (status IN ('OPEN', 'CONFIRMED', 'REJECTED', 'CORRECTED', 'IGNORED'))
);

CREATE TABLE review.risk_summaries (
    risk_summary_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id uuid NOT NULL UNIQUE REFERENCES review.reviews(review_id) ON DELETE CASCADE,
    overall_risk_level varchar(20) NOT NULL,
    risk_score numeric(6,3),
    summary text NOT NULL,
    category_scores jsonb NOT NULL DEFAULT '{}'::jsonb,
    generated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_risk_level CHECK (overall_risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT ck_risk_score CHECK (risk_score IS NULL OR risk_score BETWEEN 0 AND 100)
);

CREATE TABLE review.decisions (
    decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id uuid NOT NULL REFERENCES review.reviews(review_id) ON DELETE CASCADE,
    finding_id uuid REFERENCES review.findings(finding_id) ON DELETE CASCADE,
    decision varchar(30) NOT NULL,
    reason text,
    decided_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE RESTRICT,
    decided_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_decisions_value CHECK (decision IN ('ACCEPT', 'REJECT', 'REQUEST_CORRECTION', 'WAIVE')),
    CONSTRAINT ck_decisions_reason CHECK (decision = 'ACCEPT' OR nullif(btrim(reason), '') IS NOT NULL)
);

CREATE INDEX idx_reviews_case ON review.reviews(case_id, started_at DESC);
CREATE INDEX idx_findings_review_status ON review.findings(review_id, status, severity);

-- history
CREATE TABLE history.case_events (
    case_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL REFERENCES valuation.cases(case_id) ON DELETE RESTRICT,
    event_type varchar(80) NOT NULL,
    event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE SET NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE history.case_versions (
    case_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL REFERENCES valuation.cases(case_id) ON DELETE RESTRICT,
    version_no integer NOT NULL,
    snapshot jsonb NOT NULL,
    change_summary text,
    created_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (case_id, version_no),
    CONSTRAINT ck_case_versions_no CHECK (version_no > 0)
);

CREATE TABLE history.change_logs (
    change_log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL REFERENCES valuation.cases(case_id) ON DELETE RESTRICT,
    entity_type varchar(100) NOT NULL,
    entity_id uuid NOT NULL,
    field_name varchar(100) NOT NULL,
    old_value jsonb,
    new_value jsonb,
    change_reason text,
    changed_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE SET NULL,
    changed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_history_change_logs_changed CHECK (old_value IS DISTINCT FROM new_value)
);

CREATE TABLE history.access_logs (
    access_log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES auth.users(user_id) ON DELETE SET NULL,
    case_id uuid REFERENCES valuation.cases(case_id) ON DELETE SET NULL,
    resource_type varchar(100) NOT NULL,
    resource_id uuid,
    action varchar(50) NOT NULL,
    ip_address inet,
    user_agent text,
    accessed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_case_events_case_time ON history.case_events(case_id, occurred_at DESC);
CREATE INDEX idx_case_versions_case ON history.case_versions(case_id, version_no DESC);
CREATE INDEX idx_history_change_logs_case_time ON history.change_logs(case_id, changed_at DESC);
CREATE INDEX idx_access_logs_user_time ON history.access_logs(user_id, accessed_at DESC);
CREATE INDEX idx_access_logs_case_time ON history.access_logs(case_id, accessed_at DESC);

COMMENT ON SCHEMA auth IS '使用者、角色與權限';
COMMENT ON SCHEMA review IS '智慧審查、缺件、疑點、風險與人工決策';
COMMENT ON SCHEMA history IS '案件事件、版本、修改與調閱履歷';

COMMIT;
