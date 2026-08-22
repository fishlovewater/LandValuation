-- 001 核心資料庫：土地市價查估輔助系統 - PostgreSQL Schema v2
-- 適用：PostgreSQL 15+
-- 範圍：案件、四種查估表、比較因素、估價結果、檢核與修改履歷
-- 不包含：正式簽核、電子簽章、完整身分與權限系統
-- RAG為選配模組，請另行執行002_optional_rag_schema.sql。
-- 本核心Schema不引用rag.*，因此未安裝或未完成RAG不影響核心估價流程。

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS valuation;
SET search_path TO valuation, public;

-- ============================================================
-- 共用函式
-- ============================================================

CREATE OR REPLACE FUNCTION valuation.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- ============================================================
-- 1. 案件、宗地、文件與表單版本
-- ============================================================

CREATE TABLE cases (
    case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_no varchar(50) NOT NULL,
    case_title varchar(200) NOT NULL,
    case_type varchar(50) NOT NULL,
    requesting_agency varchar(200),
    valuation_base_date date NOT NULL,
    city_code varchar(20) NOT NULL,
    district_code varchar(20) NOT NULL,
    land_use_type varchar(100),
    case_status varchar(30) NOT NULL DEFAULT 'DRAFT',
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_cases_case_no UNIQUE (case_no),
    CONSTRAINT ck_cases_status CHECK (
        case_status IN ('DRAFT', 'PROCESSING', 'REVIEWING', 'CORRECTION', 'COMPLETED', 'ARCHIVED')
    )
);

CREATE TABLE parcels (
    parcel_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    district_code varchar(20) NOT NULL,
    section_name varchar(100) NOT NULL,
    subsection_name varchar(100) NOT NULL DEFAULT '',
    land_no varchar(50) NOT NULL,
    area_sqm numeric(18,4) NOT NULL,
    land_use_zone varchar(100),
    designated_use varchar(100),
    ownership_numerator numeric(18,6),
    ownership_denominator numeric(18,6),
    source_document_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_parcels_case
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_parcels_business_key
        UNIQUE (case_id, district_code, section_name, subsection_name, land_no),
    CONSTRAINT uq_parcels_case_parcel UNIQUE (case_id, parcel_id),
    CONSTRAINT ck_parcels_area_positive CHECK (area_sqm > 0),
    CONSTRAINT ck_parcels_ownership CHECK (
        (ownership_numerator IS NULL AND ownership_denominator IS NULL)
        OR (
            ownership_numerator IS NOT NULL
            AND ownership_denominator IS NOT NULL
            AND ownership_numerator > 0
            AND ownership_denominator > 0
            AND ownership_numerator <= ownership_denominator
        )
    )
);

CREATE TABLE documents (
    document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    document_type varchar(50) NOT NULL,
    original_filename varchar(255) NOT NULL,
    mime_type varchar(100),
    storage_key varchar(1000) NOT NULL,
    checksum_sha256 char(64) NOT NULL,
    file_size_bytes bigint,
    version_no integer NOT NULL DEFAULT 1,
    uploaded_by_user_id uuid,
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT fk_documents_case
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_documents_storage_key UNIQUE (storage_key),
    CONSTRAINT uq_documents_case_document UNIQUE (case_id, document_id),
    CONSTRAINT uq_documents_case_checksum UNIQUE (case_id, checksum_sha256),
    CONSTRAINT ck_documents_version_positive CHECK (version_no > 0),
    CONSTRAINT ck_documents_size_nonnegative CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    CONSTRAINT ck_documents_sha256 CHECK (checksum_sha256 ~ '^[0-9a-fA-F]{64}$')
);

ALTER TABLE parcels
    ADD CONSTRAINT fk_parcels_source_document
    FOREIGN KEY (case_id, source_document_id) REFERENCES documents(case_id, document_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT;

CREATE TABLE form_instances (
    form_instance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    form_code varchar(10) NOT NULL,
    version_no integer NOT NULL DEFAULT 1,
    form_status varchar(30) NOT NULL DEFAULT 'DRAFT',
    prepared_date date,
    source_document_id uuid,
    output_document_id uuid,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_form_instances_case
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_form_instances_source_document
        FOREIGN KEY (case_id, source_document_id) REFERENCES documents(case_id, document_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_form_instances_output_document
        FOREIGN KEY (case_id, output_document_id) REFERENCES documents(case_id, document_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_form_instances_version UNIQUE (case_id, form_code, version_no),
    CONSTRAINT uq_form_instances_case_instance UNIQUE (case_id, form_instance_id),
    CONSTRAINT ck_form_instances_code CHECK (form_code IN ('F01', 'F02', 'F03', 'F04')),
    CONSTRAINT ck_form_instances_version_positive CHECK (version_no > 0),
    CONSTRAINT ck_form_instances_status CHECK (
        form_status IN ('DRAFT', 'READY', 'CHECKED', 'FINAL', 'VOID')
    )
);

-- ============================================================
-- 2. 規則與因素目錄
-- ============================================================

CREATE TABLE rule_versions (
    rule_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_set_code varchar(50) NOT NULL,
    version_no integer NOT NULL,
    version_name varchar(200) NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    status varchar(20) NOT NULL DEFAULT 'DRAFT',
    source_reference varchar(1000),
    source_checksum_sha256 char(64),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_rule_versions_set_version UNIQUE (rule_set_code, version_no),
    CONSTRAINT ck_rule_versions_version_positive CHECK (version_no > 0),
    CONSTRAINT ck_rule_versions_dates CHECK (effective_to IS NULL OR effective_to >= effective_from),
    CONSTRAINT ck_rule_versions_status CHECK (status IN ('DRAFT', 'PUBLISHED', 'RETIRED')),
    CONSTRAINT ck_rule_versions_checksum CHECK (
        source_checksum_sha256 IS NULL OR source_checksum_sha256 ~ '^[0-9a-fA-F]{64}$'
    )
);

CREATE TABLE factor_definitions (
    factor_definition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    factor_code varchar(50) NOT NULL,
    factor_name varchar(100) NOT NULL,
    factor_category varchar(50) NOT NULL,
    data_type varchar(20) NOT NULL,
    unit varchar(20),
    display_order integer NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_factor_definitions_code UNIQUE (factor_code),
    CONSTRAINT uq_factor_definitions_order UNIQUE (display_order),
    CONSTRAINT ck_factor_definitions_type CHECK (
        data_type IN ('NUMBER', 'TEXT', 'ENUM', 'BOOLEAN', 'JSON')
    ),
    CONSTRAINT ck_factor_definitions_order_positive CHECK (display_order > 0)
);

CREATE TABLE factor_levels (
    factor_level_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    factor_definition_id uuid NOT NULL,
    rule_version_id uuid NOT NULL,
    land_use_type varchar(100) NOT NULL,
    level_code varchar(50) NOT NULL,
    level_name varchar(100) NOT NULL,
    range_min numeric(18,6),
    range_max numeric(18,6),
    qualitative_value varchar(200),
    suggested_rate numeric(9,6) NOT NULL,
    maximum_impact_rate numeric(9,6) NOT NULL,
    sort_order integer NOT NULL,
    CONSTRAINT fk_factor_levels_definition
        FOREIGN KEY (factor_definition_id) REFERENCES factor_definitions(factor_definition_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_factor_levels_rule_version
        FOREIGN KEY (rule_version_id) REFERENCES rule_versions(rule_version_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_factor_levels_business_key
        UNIQUE (factor_definition_id, rule_version_id, land_use_type, level_code),
    CONSTRAINT ck_factor_levels_range CHECK (
        range_min IS NULL OR range_max IS NULL OR range_max >= range_min
    ),
    CONSTRAINT ck_factor_levels_maximum_nonnegative CHECK (maximum_impact_rate >= 0),
    CONSTRAINT ck_factor_levels_suggested_within_max CHECK (
        abs(suggested_rate) <= maximum_impact_rate
    ),
    CONSTRAINT ck_factor_levels_sort_positive CHECK (sort_order > 0)
);

-- ============================================================
-- 3. F01 買賣實例調查估價表
-- ============================================================

CREATE TABLE transaction_cases (
    transaction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    form_instance_id uuid,
    transaction_no varchar(30) NOT NULL,
    price_period varchar(10),
    price_zone_no varchar(30),
    transaction_date date NOT NULL,
    subject_address varchar(300),
    transaction_total_price numeric(20,2) NOT NULL,
    normal_total_price numeric(20,2),
    land_area_sqm numeric(18,4),
    building_cost_total numeric(20,2),
    land_rights_unit_price numeric(20,2),
    normal_land_unit_price numeric(20,2),
    article_7_8_adjustment_rate numeric(9,6) NOT NULL DEFAULT 0,
    article_7_8_reason text,
    notes text,
    record_status varchar(20) NOT NULL DEFAULT 'DRAFT',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_transaction_cases_case
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_transaction_cases_form
        FOREIGN KEY (case_id, form_instance_id)
        REFERENCES form_instances(case_id, form_instance_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_transaction_cases_no UNIQUE (case_id, transaction_no),
    CONSTRAINT uq_transaction_cases_case_transaction UNIQUE (case_id, transaction_id),
    CONSTRAINT ck_transaction_cases_total_price CHECK (transaction_total_price > 0),
    CONSTRAINT ck_transaction_cases_normal_total CHECK (normal_total_price IS NULL OR normal_total_price >= 0),
    CONSTRAINT ck_transaction_cases_land_area CHECK (land_area_sqm IS NULL OR land_area_sqm > 0),
    CONSTRAINT ck_transaction_cases_building_cost CHECK (building_cost_total IS NULL OR building_cost_total >= 0),
    CONSTRAINT ck_transaction_cases_unit_prices CHECK (
        (land_rights_unit_price IS NULL OR land_rights_unit_price >= 0)
        AND (normal_land_unit_price IS NULL OR normal_land_unit_price >= 0)
    ),
    CONSTRAINT ck_transaction_cases_adjustment_reason CHECK (
        article_7_8_adjustment_rate = 0 OR nullif(btrim(article_7_8_reason), '') IS NOT NULL
    ),
    CONSTRAINT ck_transaction_cases_status CHECK (record_status IN ('DRAFT', 'READY', 'FINAL', 'VOID'))
);

CREATE TABLE transaction_land_parcels (
    transaction_land_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id uuid NOT NULL,
    district_code varchar(20) NOT NULL,
    section_name varchar(100) NOT NULL,
    subsection_name varchar(100) NOT NULL DEFAULT '',
    land_no varchar(50) NOT NULL,
    area_sqm numeric(18,4) NOT NULL,
    ownership_numerator numeric(18,6),
    ownership_denominator numeric(18,6),
    CONSTRAINT fk_transaction_land_parcels_transaction
        FOREIGN KEY (transaction_id) REFERENCES transaction_cases(transaction_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT uq_transaction_land_parcels_business_key
        UNIQUE (transaction_id, district_code, section_name, subsection_name, land_no),
    CONSTRAINT ck_transaction_land_parcels_area CHECK (area_sqm > 0),
    CONSTRAINT ck_transaction_land_parcels_ownership CHECK (
        (ownership_numerator IS NULL AND ownership_denominator IS NULL)
        OR (
            ownership_numerator IS NOT NULL
            AND ownership_denominator IS NOT NULL
            AND ownership_numerator > 0
            AND ownership_denominator > 0
            AND ownership_numerator <= ownership_denominator
        )
    )
);

CREATE TABLE transaction_buildings (
    transaction_building_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id uuid NOT NULL,
    building_no varchar(50) NOT NULL,
    main_structure_type varchar(50),
    floors_above_ground integer,
    floors_below_ground integer,
    transferred_floor varchar(50),
    registered_area_sqm numeric(18,4),
    calculated_area_sqm numeric(18,4),
    construction_period_years numeric(8,2),
    completion_date date,
    CONSTRAINT fk_transaction_buildings_transaction
        FOREIGN KEY (transaction_id) REFERENCES transaction_cases(transaction_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT uq_transaction_buildings_no UNIQUE (transaction_id, building_no),
    CONSTRAINT ck_transaction_buildings_floors CHECK (
        (floors_above_ground IS NULL OR floors_above_ground >= 0)
        AND (floors_below_ground IS NULL OR floors_below_ground >= 0)
    ),
    CONSTRAINT ck_transaction_buildings_areas CHECK (
        (registered_area_sqm IS NULL OR registered_area_sqm > 0)
        AND (calculated_area_sqm IS NULL OR calculated_area_sqm > 0)
        AND (
            registered_area_sqm IS NULL
            OR calculated_area_sqm IS NULL
            OR calculated_area_sqm <= registered_area_sqm
        )
    ),
    CONSTRAINT ck_transaction_buildings_period CHECK (
        construction_period_years IS NULL OR construction_period_years >= 0
    )
);

CREATE TABLE transaction_financing (
    financing_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id uuid NOT NULL,
    own_funds_rate numeric(9,6) NOT NULL DEFAULT 0,
    own_funds_ratio numeric(9,6) NOT NULL DEFAULT 0,
    borrowed_funds_rate numeric(9,6) NOT NULL DEFAULT 0,
    borrowed_funds_ratio numeric(9,6) NOT NULL DEFAULT 0,
    presale_income_rate numeric(9,6) NOT NULL DEFAULT 0,
    presale_income_ratio numeric(9,6) NOT NULL DEFAULT 0,
    composite_interest_rate numeric(9,6),
    input_schedule jsonb,
    CONSTRAINT fk_transaction_financing_transaction
        FOREIGN KEY (transaction_id) REFERENCES transaction_cases(transaction_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT uq_transaction_financing_transaction UNIQUE (transaction_id),
    CONSTRAINT ck_transaction_financing_rates CHECK (
        own_funds_rate BETWEEN 0 AND 1
        AND borrowed_funds_rate BETWEEN 0 AND 1
        AND presale_income_rate BETWEEN 0 AND 1
        AND (composite_interest_rate IS NULL OR composite_interest_rate BETWEEN 0 AND 1)
    ),
    CONSTRAINT ck_transaction_financing_ratios CHECK (
        own_funds_ratio BETWEEN 0 AND 1
        AND borrowed_funds_ratio BETWEEN 0 AND 1
        AND presale_income_ratio BETWEEN 0 AND 1
        AND abs((own_funds_ratio + borrowed_funds_ratio + presale_income_ratio) - 1) <= 0.000001
    )
);

CREATE TABLE transaction_cost_items (
    cost_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id uuid NOT NULL,
    rule_version_id uuid,
    cost_item_code varchar(50) NOT NULL,
    rate numeric(9,6),
    amount numeric(20,2) NOT NULL,
    unit varchar(30) NOT NULL DEFAULT 'TWD_PER_SQM',
    input_snapshot jsonb,
    CONSTRAINT fk_transaction_cost_items_transaction
        FOREIGN KEY (transaction_id) REFERENCES transaction_cases(transaction_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_transaction_cost_items_rule_version
        FOREIGN KEY (rule_version_id) REFERENCES rule_versions(rule_version_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_transaction_cost_items_code UNIQUE (transaction_id, cost_item_code),
    CONSTRAINT ck_transaction_cost_items_rate CHECK (rate IS NULL OR rate BETWEEN 0 AND 1),
    CONSTRAINT ck_transaction_cost_items_amount CHECK (amount >= 0),
    CONSTRAINT ck_transaction_cost_items_code CHECK (
        cost_item_code IN (
            'CONSTRUCTION', 'PLANNING_DESIGN', 'ADVERTISING_SALES', 'MANAGEMENT',
            'TAX_OTHER', 'CAPITAL_INTEREST', 'DEVELOPMENT_PROFIT', 'REPLACEMENT_COST'
        )
    )
);

CREATE TABLE transaction_depreciation (
    depreciation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_building_id uuid NOT NULL,
    rule_version_id uuid,
    depreciation_method varchar(30) NOT NULL,
    elapsed_years numeric(8,2) NOT NULL,
    total_useful_life numeric(8,2) NOT NULL,
    remaining_useful_life numeric(8,2) NOT NULL,
    salvage_value_rate numeric(9,6) NOT NULL DEFAULT 0,
    accumulated_depreciation_per_sqm numeric(20,2) NOT NULL,
    formula_snapshot text NOT NULL,
    CONSTRAINT fk_transaction_depreciation_building
        FOREIGN KEY (transaction_building_id) REFERENCES transaction_buildings(transaction_building_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_transaction_depreciation_rule_version
        FOREIGN KEY (rule_version_id) REFERENCES rule_versions(rule_version_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_transaction_depreciation_building UNIQUE (transaction_building_id),
    CONSTRAINT ck_transaction_depreciation_method CHECK (depreciation_method IN ('STRAIGHT_LINE', 'OTHER')),
    CONSTRAINT ck_transaction_depreciation_years CHECK (
        elapsed_years >= 0
        AND total_useful_life > 0
        AND remaining_useful_life >= 0
        AND abs((elapsed_years + remaining_useful_life) - total_useful_life) <= 0.02
    ),
    CONSTRAINT ck_transaction_depreciation_salvage CHECK (salvage_value_rate BETWEEN 0 AND 1),
    CONSTRAINT ck_transaction_depreciation_amount CHECK (accumulated_depreciation_per_sqm >= 0)
);

-- ============================================================
-- 4. F02 比較法調查估價表
-- ============================================================

CREATE TABLE benchmark_lands (
    benchmark_land_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    parcel_id uuid NOT NULL,
    benchmark_land_no varchar(30) NOT NULL,
    price_zone_no varchar(30) NOT NULL,
    land_consolidation_serial varchar(30),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_benchmark_lands_case
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_benchmark_lands_parcel_same_case
        FOREIGN KEY (case_id, parcel_id) REFERENCES parcels(case_id, parcel_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_benchmark_lands_no UNIQUE (case_id, benchmark_land_no),
    CONSTRAINT uq_benchmark_lands_case_benchmark UNIQUE (case_id, benchmark_land_id)
);

CREATE UNIQUE INDEX uq_benchmark_lands_active_parcel
    ON benchmark_lands(case_id, parcel_id)
    WHERE is_active;

CREATE TABLE comparison_analyses (
    comparison_analysis_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    benchmark_land_id uuid NOT NULL,
    form_instance_id uuid,
    valuation_base_date date NOT NULL,
    benchmark_comparison_price numeric(20,2),
    benchmark_condition_notes text,
    notes text,
    analysis_status varchar(20) NOT NULL DEFAULT 'DRAFT',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_comparison_analyses_case
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_comparison_analyses_benchmark_same_case
        FOREIGN KEY (case_id, benchmark_land_id)
        REFERENCES benchmark_lands(case_id, benchmark_land_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_comparison_analyses_form_same_case
        FOREIGN KEY (case_id, form_instance_id)
        REFERENCES form_instances(case_id, form_instance_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_comparison_analyses_form UNIQUE (form_instance_id),
    CONSTRAINT uq_comparison_analyses_case_analysis UNIQUE (case_id, comparison_analysis_id),
    CONSTRAINT ck_comparison_analyses_price CHECK (
        benchmark_comparison_price IS NULL OR benchmark_comparison_price >= 0
    ),
    CONSTRAINT ck_comparison_analyses_status CHECK (
        analysis_status IN ('DRAFT', 'READY', 'FINAL', 'VOID')
    )
);

CREATE TABLE comparison_targets (
    comparison_target_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    comparison_analysis_id uuid NOT NULL,
    transaction_id uuid NOT NULL,
    normal_unit_price_snapshot numeric(20,2) NOT NULL,
    transaction_date_snapshot date NOT NULL,
    time_adjustment_rate numeric(9,6) NOT NULL DEFAULT 0,
    regional_adjustment_rate numeric(9,6) NOT NULL DEFAULT 0,
    total_adjustment_absolute numeric(9,6),
    trial_price numeric(20,2),
    weight numeric(9,6),
    similarity_level varchar(20),
    condition_notes text,
    CONSTRAINT fk_comparison_targets_analysis
        FOREIGN KEY (case_id, comparison_analysis_id)
        REFERENCES comparison_analyses(case_id, comparison_analysis_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_comparison_targets_transaction
        FOREIGN KEY (case_id, transaction_id)
        REFERENCES transaction_cases(case_id, transaction_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_comparison_targets_transaction UNIQUE (comparison_analysis_id, transaction_id),
    CONSTRAINT ck_comparison_targets_prices CHECK (
        normal_unit_price_snapshot >= 0 AND (trial_price IS NULL OR trial_price >= 0)
    ),
    CONSTRAINT ck_comparison_targets_absolute CHECK (
        total_adjustment_absolute IS NULL OR total_adjustment_absolute >= 0
    ),
    CONSTRAINT ck_comparison_targets_weight CHECK (weight IS NULL OR weight BETWEEN 0 AND 1),
    CONSTRAINT ck_comparison_targets_similarity CHECK (
        similarity_level IS NULL OR similarity_level IN ('HIGH', 'MEDIUM', 'LOW')
    )
);

CREATE TABLE comparison_factor_values (
    factor_value_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    comparison_target_id uuid NOT NULL,
    factor_definition_id uuid NOT NULL,
    factor_level_id uuid,
    benchmark_number numeric(20,6),
    benchmark_text text,
    benchmark_json jsonb,
    comparable_number numeric(20,6),
    comparable_text text,
    comparable_json jsonb,
    suggested_rate numeric(9,6),
    adopted_rate numeric(9,6) NOT NULL DEFAULT 0,
    adjustment_reason text,
    CONSTRAINT fk_comparison_factor_values_target
        FOREIGN KEY (comparison_target_id) REFERENCES comparison_targets(comparison_target_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_comparison_factor_values_definition
        FOREIGN KEY (factor_definition_id) REFERENCES factor_definitions(factor_definition_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_comparison_factor_values_level
        FOREIGN KEY (factor_level_id) REFERENCES factor_levels(factor_level_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_comparison_factor_values_target_factor
        UNIQUE (comparison_target_id, factor_definition_id),
    CONSTRAINT ck_comparison_factor_values_benchmark_one_type CHECK (
        num_nonnulls(benchmark_number, benchmark_text, benchmark_json) <= 1
    ),
    CONSTRAINT ck_comparison_factor_values_comparable_one_type CHECK (
        num_nonnulls(comparable_number, comparable_text, comparable_json) <= 1
    ),
    CONSTRAINT ck_comparison_factor_values_reason CHECK (
        suggested_rate IS NULL
        OR abs(adopted_rate - suggested_rate) <= 0.000001
        OR nullif(btrim(adjustment_reason), '') IS NOT NULL
    )
);

-- ============================================================
-- 5. F03 比準地地價估計表
-- ============================================================

CREATE TABLE benchmark_valuations (
    benchmark_valuation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    benchmark_land_id uuid NOT NULL,
    comparison_analysis_id uuid,
    form_instance_id uuid,
    valuation_base_date date NOT NULL,
    comparison_price numeric(20,2),
    comparison_weight numeric(9,6) NOT NULL DEFAULT 1,
    income_price numeric(20,2),
    income_weight numeric(9,6) NOT NULL DEFAULT 0,
    benchmark_land_price numeric(20,2),
    market_period_start date,
    market_period_end date,
    market_condition text,
    selection_scope_reason text,
    decision_reason text,
    version_no integer NOT NULL DEFAULT 1,
    valuation_status varchar(20) NOT NULL DEFAULT 'DRAFT',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_benchmark_valuations_case
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_benchmark_valuations_benchmark_same_case
        FOREIGN KEY (case_id, benchmark_land_id)
        REFERENCES benchmark_lands(case_id, benchmark_land_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_benchmark_valuations_analysis_same_case
        FOREIGN KEY (case_id, comparison_analysis_id)
        REFERENCES comparison_analyses(case_id, comparison_analysis_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_benchmark_valuations_form_same_case
        FOREIGN KEY (case_id, form_instance_id)
        REFERENCES form_instances(case_id, form_instance_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_benchmark_valuations_version UNIQUE (benchmark_land_id, version_no),
    CONSTRAINT uq_benchmark_valuations_form UNIQUE (form_instance_id),
    CONSTRAINT uq_benchmark_valuations_case_valuation UNIQUE (case_id, benchmark_valuation_id),
    CONSTRAINT ck_benchmark_valuations_prices CHECK (
        (comparison_price IS NULL OR comparison_price >= 0)
        AND (income_price IS NULL OR income_price >= 0)
        AND (benchmark_land_price IS NULL OR benchmark_land_price >= 0)
    ),
    CONSTRAINT ck_benchmark_valuations_weights CHECK (
        comparison_weight BETWEEN 0 AND 1
        AND income_weight BETWEEN 0 AND 1
        AND abs((comparison_weight + income_weight) - 1) <= 0.000001
    ),
    CONSTRAINT ck_benchmark_valuations_method_inputs CHECK (
        valuation_status = 'DRAFT'
        OR (
            (comparison_weight = 0 OR comparison_price IS NOT NULL)
            AND (income_weight = 0 OR income_price IS NOT NULL)
        )
    ),
    CONSTRAINT ck_benchmark_valuations_market_period CHECK (
        market_period_start IS NULL
        OR market_period_end IS NULL
        OR market_period_end >= market_period_start
    ),
    CONSTRAINT ck_benchmark_valuations_version_positive CHECK (version_no > 0),
    CONSTRAINT ck_benchmark_valuations_status CHECK (
        valuation_status IN ('DRAFT', 'READY', 'FINAL', 'VOID')
    ),
    CONSTRAINT ck_benchmark_valuations_completion CHECK (
        valuation_status IN ('DRAFT', 'VOID')
        OR (
            benchmark_land_price IS NOT NULL
            AND nullif(btrim(market_condition), '') IS NOT NULL
            AND nullif(btrim(decision_reason), '') IS NOT NULL
        )
    )
);

CREATE UNIQUE INDEX uq_benchmark_valuations_one_final
    ON benchmark_valuations(benchmark_land_id)
    WHERE valuation_status = 'FINAL';

-- ============================================================
-- 6. F04 徵收土地宗地市價估計表
-- ============================================================

CREATE TABLE parcel_valuations (
    parcel_valuation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    benchmark_valuation_id uuid NOT NULL,
    form_instance_id uuid,
    valuation_base_date date NOT NULL,
    price_zone_no varchar(30) NOT NULL,
    version_no integer NOT NULL DEFAULT 1,
    valuation_status varchar(20) NOT NULL DEFAULT 'DRAFT',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_parcel_valuations_case
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_parcel_valuations_benchmark_same_case
        FOREIGN KEY (case_id, benchmark_valuation_id)
        REFERENCES benchmark_valuations(case_id, benchmark_valuation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_parcel_valuations_form_same_case
        FOREIGN KEY (case_id, form_instance_id)
        REFERENCES form_instances(case_id, form_instance_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_parcel_valuations_version
        UNIQUE (case_id, benchmark_valuation_id, version_no),
    CONSTRAINT uq_parcel_valuations_case_valuation
        UNIQUE (case_id, parcel_valuation_id),
    CONSTRAINT uq_parcel_valuations_form UNIQUE (form_instance_id),
    CONSTRAINT ck_parcel_valuations_version_positive CHECK (version_no > 0),
    CONSTRAINT ck_parcel_valuations_status CHECK (
        valuation_status IN ('DRAFT', 'READY', 'FINAL', 'VOID')
    )
);

CREATE TABLE parcel_valuation_items (
    parcel_valuation_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    parcel_valuation_id uuid NOT NULL,
    parcel_id uuid NOT NULL,
    parcel_serial varchar(30) NOT NULL,
    benchmark_price_snapshot numeric(20,2) NOT NULL,
    comparison_price numeric(20,2),
    comparison_weight numeric(9,6) NOT NULL DEFAULT 1,
    income_price numeric(20,2),
    income_weight numeric(9,6) NOT NULL DEFAULT 0,
    adjustment_rate numeric(9,6) NOT NULL DEFAULT 0,
    parcel_unit_price numeric(20,2),
    pre_split_condition text,
    adjustment_explanation text,
    decision_reason text,
    CONSTRAINT fk_parcel_valuation_items_valuation
        FOREIGN KEY (case_id, parcel_valuation_id)
        REFERENCES parcel_valuations(case_id, parcel_valuation_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_parcel_valuation_items_parcel
        FOREIGN KEY (case_id, parcel_id) REFERENCES parcels(case_id, parcel_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_parcel_valuation_items_parcel UNIQUE (parcel_valuation_id, parcel_id),
    CONSTRAINT uq_parcel_valuation_items_serial UNIQUE (parcel_valuation_id, parcel_serial),
    CONSTRAINT ck_parcel_valuation_items_prices CHECK (
        benchmark_price_snapshot >= 0
        AND (comparison_price IS NULL OR comparison_price >= 0)
        AND (income_price IS NULL OR income_price >= 0)
        AND (parcel_unit_price IS NULL OR parcel_unit_price >= 0)
    ),
    CONSTRAINT ck_parcel_valuation_items_weights CHECK (
        comparison_weight BETWEEN 0 AND 1
        AND income_weight BETWEEN 0 AND 1
        AND abs((comparison_weight + income_weight) - 1) <= 0.000001
    ),
    CONSTRAINT ck_parcel_valuation_items_adjustment_reason CHECK (
        adjustment_rate = 0 OR nullif(btrim(adjustment_explanation), '') IS NOT NULL
    )
);

-- ============================================================
-- 7. 檢核規則、檢核結果與修改履歷
-- ============================================================

CREATE TABLE validation_rules (
    validation_rule_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_version_id uuid NOT NULL,
    rule_code varchar(80) NOT NULL,
    rule_name varchar(200) NOT NULL,
    target_form_code varchar(10),
    target_table varchar(100) NOT NULL,
    target_field_code varchar(100),
    severity varchar(20) NOT NULL,
    rule_expression text NOT NULL,
    message_template text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_validation_rules_rule_version
        FOREIGN KEY (rule_version_id) REFERENCES rule_versions(rule_version_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_validation_rules_version_code UNIQUE (rule_version_id, rule_code),
    CONSTRAINT ck_validation_rules_form_code CHECK (
        target_form_code IS NULL OR target_form_code IN ('F01', 'F02', 'F03', 'F04')
    ),
    CONSTRAINT ck_validation_rules_severity CHECK (
        severity IN ('LOW', 'MEDIUM', 'HIGH', 'MISSING_DATA')
    )
);

CREATE TABLE validation_runs (
    validation_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    form_instance_id uuid,
    run_status varchar(20) NOT NULL DEFAULT 'RUNNING',
    passed_count integer NOT NULL DEFAULT 0,
    warning_count integer NOT NULL DEFAULT 0,
    failed_count integer NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    triggered_by_user_id uuid,
    CONSTRAINT fk_validation_runs_case
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_validation_runs_form_same_case
        FOREIGN KEY (case_id, form_instance_id)
        REFERENCES form_instances(case_id, form_instance_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_validation_runs_status CHECK (
        run_status IN ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')
    ),
    CONSTRAINT ck_validation_runs_counts CHECK (
        passed_count >= 0 AND warning_count >= 0 AND failed_count >= 0
    ),
    CONSTRAINT ck_validation_runs_times CHECK (
        completed_at IS NULL OR completed_at >= started_at
    )
);

CREATE TABLE validation_findings (
    finding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    validation_run_id uuid NOT NULL,
    validation_rule_id uuid NOT NULL,
    entity_type varchar(100),
    entity_id uuid,
    field_code varchar(100),
    severity varchar(20) NOT NULL,
    actual_value jsonb,
    expected_value jsonb,
    finding_message text NOT NULL,
    handling_status varchar(20) NOT NULL DEFAULT 'OPEN',
    manual_decision varchar(20),
    decision_reason text,
    decided_by_user_id uuid,
    decided_at timestamptz,
    CONSTRAINT fk_validation_findings_run
        FOREIGN KEY (validation_run_id) REFERENCES validation_runs(validation_run_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_validation_findings_rule
        FOREIGN KEY (validation_rule_id) REFERENCES validation_rules(validation_rule_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_validation_findings_severity CHECK (
        severity IN ('LOW', 'MEDIUM', 'HIGH', 'MISSING_DATA')
    ),
    CONSTRAINT ck_validation_findings_status CHECK (
        handling_status IN ('OPEN', 'ACCEPTED', 'REJECTED', 'CORRECTED', 'IGNORED')
    ),
    CONSTRAINT ck_validation_findings_decision CHECK (
        manual_decision IS NULL OR manual_decision IN ('ACCEPT_AI', 'REJECT_AI', 'MODIFY')
    ),
    CONSTRAINT ck_validation_findings_decision_reason CHECK (
        manual_decision IS NULL
        OR manual_decision = 'ACCEPT_AI'
        OR nullif(btrim(decision_reason), '') IS NOT NULL
    )
);

CREATE TABLE change_logs (
    change_log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    form_instance_id uuid,
    entity_type varchar(100) NOT NULL,
    entity_id uuid NOT NULL,
    field_name varchar(100) NOT NULL,
    old_value jsonb,
    new_value jsonb,
    changed_by_user_id uuid,
    changed_at timestamptz NOT NULL DEFAULT now(),
    change_reason text,
    CONSTRAINT fk_change_logs_case
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_change_logs_form_same_case
        FOREIGN KEY (case_id, form_instance_id)
        REFERENCES form_instances(case_id, form_instance_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_change_logs_value_changed CHECK (old_value IS DISTINCT FROM new_value)
);

-- ============================================================
-- 8. updated_at triggers
-- ============================================================

CREATE TRIGGER trg_cases_updated_at
BEFORE UPDATE ON cases
FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();

CREATE TRIGGER trg_parcels_updated_at
BEFORE UPDATE ON parcels
FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();

CREATE TRIGGER trg_form_instances_updated_at
BEFORE UPDATE ON form_instances
FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();

CREATE TRIGGER trg_factor_definitions_updated_at
BEFORE UPDATE ON factor_definitions
FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();

CREATE TRIGGER trg_transaction_cases_updated_at
BEFORE UPDATE ON transaction_cases
FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();

CREATE TRIGGER trg_benchmark_lands_updated_at
BEFORE UPDATE ON benchmark_lands
FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();

CREATE TRIGGER trg_comparison_analyses_updated_at
BEFORE UPDATE ON comparison_analyses
FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();

CREATE TRIGGER trg_benchmark_valuations_updated_at
BEFORE UPDATE ON benchmark_valuations
FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();

CREATE TRIGGER trg_parcel_valuations_updated_at
BEFORE UPDATE ON parcel_valuations
FOR EACH ROW EXECUTE FUNCTION valuation.set_updated_at();

-- ============================================================
-- 9. 查詢與關聯索引
-- PostgreSQL 不會自動替外鍵建立索引，因此明確建立常用FK索引。
-- ============================================================

CREATE INDEX idx_cases_status_base_date
    ON cases(case_status, valuation_base_date DESC);

CREATE INDEX idx_cases_location
    ON cases(city_code, district_code, valuation_base_date DESC);

CREATE INDEX idx_parcels_case
    ON parcels(case_id);

CREATE INDEX idx_parcels_land_lookup
    ON parcels(district_code, section_name, subsection_name, land_no);

CREATE INDEX idx_documents_case_type
    ON documents(case_id, document_type, uploaded_at DESC);

CREATE INDEX idx_documents_active
    ON documents(case_id, uploaded_at DESC)
    WHERE is_active;

CREATE INDEX idx_form_instances_case_status
    ON form_instances(case_id, form_code, form_status, version_no DESC);

CREATE UNIQUE INDEX uq_form_instances_one_final
    ON form_instances(case_id, form_code)
    WHERE form_status = 'FINAL';

CREATE INDEX idx_rule_versions_effective
    ON rule_versions(rule_set_code, effective_from, effective_to)
    WHERE status = 'PUBLISHED';

CREATE INDEX idx_factor_definitions_category
    ON factor_definitions(factor_category, display_order)
    WHERE is_active;

CREATE INDEX idx_factor_levels_lookup
    ON factor_levels(factor_definition_id, rule_version_id, land_use_type, sort_order);

CREATE INDEX idx_transaction_cases_case_date
    ON transaction_cases(case_id, transaction_date DESC);

CREATE INDEX idx_transaction_cases_price_zone
    ON transaction_cases(price_zone_no, transaction_date DESC);

CREATE INDEX idx_transaction_cases_normal_unit_price
    ON transaction_cases(normal_land_unit_price)
    WHERE record_status = 'FINAL' AND normal_land_unit_price IS NOT NULL;

CREATE INDEX idx_transaction_land_parcels_transaction
    ON transaction_land_parcels(transaction_id);

CREATE INDEX idx_transaction_land_parcels_location
    ON transaction_land_parcels(district_code, section_name, subsection_name, land_no);

CREATE INDEX idx_transaction_buildings_transaction
    ON transaction_buildings(transaction_id);

CREATE INDEX idx_transaction_cost_items_rule
    ON transaction_cost_items(rule_version_id);

CREATE INDEX idx_transaction_depreciation_rule
    ON transaction_depreciation(rule_version_id);

CREATE INDEX idx_benchmark_lands_case
    ON benchmark_lands(case_id, is_active);

CREATE INDEX idx_comparison_analyses_benchmark
    ON comparison_analyses(benchmark_land_id, valuation_base_date DESC);

CREATE INDEX idx_comparison_targets_analysis
    ON comparison_targets(case_id, comparison_analysis_id);

CREATE INDEX idx_comparison_targets_transaction
    ON comparison_targets(case_id, transaction_id);

CREATE INDEX idx_comparison_factor_values_target
    ON comparison_factor_values(comparison_target_id);

CREATE INDEX idx_comparison_factor_values_factor
    ON comparison_factor_values(factor_definition_id);

CREATE INDEX idx_comparison_factor_values_level
    ON comparison_factor_values(factor_level_id)
    WHERE factor_level_id IS NOT NULL;

CREATE INDEX idx_benchmark_valuations_case_date
    ON benchmark_valuations(case_id, valuation_base_date DESC);

CREATE INDEX idx_benchmark_valuations_analysis
    ON benchmark_valuations(comparison_analysis_id)
    WHERE comparison_analysis_id IS NOT NULL;

CREATE INDEX idx_parcel_valuations_case_date
    ON parcel_valuations(case_id, valuation_base_date DESC);

CREATE INDEX idx_parcel_valuations_benchmark
    ON parcel_valuations(benchmark_valuation_id);

CREATE INDEX idx_parcel_valuation_items_valuation
    ON parcel_valuation_items(case_id, parcel_valuation_id);

CREATE INDEX idx_parcel_valuation_items_parcel
    ON parcel_valuation_items(case_id, parcel_id);

CREATE INDEX idx_validation_rules_active_target
    ON validation_rules(target_form_code, target_table, target_field_code)
    WHERE is_active;

CREATE INDEX idx_validation_runs_case_started
    ON validation_runs(case_id, started_at DESC);

CREATE INDEX idx_validation_runs_form_started
    ON validation_runs(form_instance_id, started_at DESC)
    WHERE form_instance_id IS NOT NULL;

CREATE INDEX idx_validation_findings_run_status
    ON validation_findings(validation_run_id, handling_status, severity);

CREATE INDEX idx_validation_findings_open
    ON validation_findings(severity, finding_id)
    WHERE handling_status = 'OPEN';

CREATE INDEX idx_validation_findings_entity
    ON validation_findings(entity_type, entity_id)
    WHERE entity_id IS NOT NULL;

CREATE INDEX idx_change_logs_case_time
    ON change_logs(case_id, changed_at DESC);

CREATE INDEX idx_change_logs_entity
    ON change_logs(entity_type, entity_id, changed_at DESC);

-- ============================================================
-- 10. 權重合計驗證函式
-- 在送出READY或FINAL前由後端呼叫；避免編輯途中被逐列trigger阻擋。
-- ============================================================

CREATE OR REPLACE FUNCTION valuation.check_comparison_weights(
    p_comparison_analysis_id uuid
)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT
        count(*) > 0
        AND bool_and(weight IS NOT NULL)
        AND abs(coalesce(sum(weight), 0) - 1) <= 0.000001
    FROM valuation.comparison_targets
    WHERE comparison_analysis_id = p_comparison_analysis_id;
$$;

COMMENT ON FUNCTION valuation.check_comparison_weights(uuid) IS
'確認指定比較法分析至少有一個比較標的、每筆皆有權重且權重合計為1。送出READY或FINAL前由服務層呼叫。';

CREATE OR REPLACE FUNCTION valuation.check_parcel_valuation_complete(
    p_parcel_valuation_id uuid
)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT
        count(*) > 0
        AND bool_and(parcel_unit_price IS NOT NULL)
        AND bool_and(nullif(btrim(decision_reason), '') IS NOT NULL)
        AND bool_and(comparison_weight = 0 OR comparison_price IS NOT NULL)
        AND bool_and(income_weight = 0 OR income_price IS NOT NULL)
    FROM valuation.parcel_valuation_items
    WHERE parcel_valuation_id = p_parcel_valuation_id;
$$;

COMMENT ON FUNCTION valuation.check_parcel_valuation_complete(uuid) IS
'確認宗地估價至少包含一筆宗地，且各宗地價格、決定理由及採用方法輸入完整。送出READY或FINAL前由服務層呼叫。';

-- ============================================================
-- 11. 表格說明
-- ============================================================

COMMENT ON SCHEMA valuation IS '土地市價查估輔助系統核心資料庫第一版';
COMMENT ON TABLE cases IS '案件主檔，保存目前有效的案件基本資料與操作履歷';
COMMENT ON TABLE parcels IS '案件宗地，一個案件可包含多筆段、小段、地號';
COMMENT ON TABLE documents IS '案件文件Metadata，檔案本體存物件儲存空間';
COMMENT ON TABLE form_instances IS '四種查估表的版本與狀態，不保存正式簽核';
COMMENT ON TABLE rule_versions IS '公式、評價基準、因素級距與檢核規則的版本主檔';
COMMENT ON TABLE factor_definitions IS '比較法個別因素目錄';
COMMENT ON TABLE factor_levels IS '依用地類型與規則版本設定因素級距及建議修正率';
COMMENT ON TABLE transaction_cases IS 'F01買賣實例調查估價表主資料及土地正常單價';
COMMENT ON TABLE transaction_cost_items IS '買賣實例成本項目，一項成本一筆資料';
COMMENT ON TABLE comparison_analyses IS 'F02針對一筆比準地執行的一次比較法分析';
COMMENT ON TABLE comparison_targets IS '比較法採用的買賣實例、修正率、試算價格與權重';
COMMENT ON TABLE comparison_factor_values IS '每個比較標的對應的各項因素條件、建議率及採用率';
COMMENT ON TABLE benchmark_valuations IS 'F03比準地地價估計結果與決定理由';
COMMENT ON TABLE parcel_valuations IS 'F04宗地市價估計作業表頭及版本';
COMMENT ON TABLE parcel_valuation_items IS 'F04每一宗地的修正、價格與決定理由';
COMMENT ON TABLE validation_rules IS '可版本化的欄位、公式及跨表檢核規則';
COMMENT ON TABLE validation_findings IS '檢核疑點及人工接受、拒絕或修改結果';
COMMENT ON TABLE change_logs IS '欄位修改前後值與操作人紀錄，不代表正式簽核';

COMMIT;
