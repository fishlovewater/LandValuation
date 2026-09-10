import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const htmlPath = path.join(here, "..", "app", "valuation", "test_ui", "index.html");

function loadLogic(runtime = {}) {
  const html = fs.readFileSync(htmlPath, "utf8");
  const match = html.match(/<script>\s*([\s\S]*?)\s<\/script>/i);
  assert.ok(match, "test page should expose a dependency-free behavior script");
  const context = {
    console,
    URL,
    setTimeout,
    clearTimeout,
    window: {},
    ...runtime,
  };
  vm.runInNewContext(match[1], context, { filename: htmlPath });
  assert.ok(context.window.valuationUiLogic);
  return { logic: context.window.valuationUiLogic, context };
}

function fakeForm(values, files = []) {
  const controls = Object.entries(values).map(([name, value]) => ({
    name,
    value,
    checked: typeof value === "boolean" ? value : undefined,
    type: typeof value === "boolean" ? "checkbox" : "text",
  }));
  controls.push({ name: "source_files", type: "file", files });
  return {
    elements: {
      namedItem(name) {
        return controls.find((control) => control.name === name) || null;
      },
    },
    querySelectorAll(selector) {
      if (selector.includes("category_override")) {
        return controls.filter((control) => control.name === "category_override");
      }
      return [];
    },
  };
}

function fakeElement(overrides = {}) {
  const listeners = Object.create(null);
  return Object.assign({
    disabled: false,
    hidden: false,
    value: "",
    textContent: "",
    innerHTML: "",
    dataset: {},
    classList: { toggle() {} },
    addEventListener(type, handler) {
      listeners[type] = handler;
    },
    getListener(type) {
      return listeners[type];
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  }, overrides);
}

function fakeDocument(elements = {}, querySelectorAll = () => []) {
  return {
    getElementById(id) {
      return elements[id] || null;
    },
    querySelectorAll,
  };
}

function candidateWorkflow(overrides = {}) {
  return Object.assign({
    case: { case_id: "case-1", case_title: "測試案件" },
    report_id: "report-1",
    documents: [],
    candidates: [{
      extracted_field_id: "f1",
      document_id: "d1",
      field_name: "transaction_total_price",
      extracted_value: "100",
      field_status: "NEEDS_CONFIRMATION",
      source_page: 1,
      source_text: "交易總價 100",
      confidence: 0.9,
    }],
  }, overrides);
}

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    async json() {
      return payload;
    },
  };
}

function casePanelElements() {
  return Object.fromEntries([
    "status-message",
    "candidate-summary",
    "candidate-list",
    "candidate-action-message",
    "confirm-candidates",
    "refresh-candidates",
    "formal-check",
    "formal-summary",
    "formal-findings",
    "formal-action-reason",
    "run-formal-workflow",
    "download-formal-report",
    "submit-for-review",
    "correction-message",
    "missing-items",
    "request-log",
    "form-selector",
  ].map((id) => [id, fakeElement()]));
}

test("builds an explicit confirmation request", () => {
  const { logic } = loadLogic();

  assert.deepEqual(
    logic.buildConfirmationRequest([
      {
        document_id: "d1",
        extracted_field_id: "f1",
        choice: "CONFIRM",
        corrected_value: "120",
      },
      {
        document_id: "d2",
        extracted_field_id: "f2",
        choice: "REJECT",
        corrected_value: "ignored",
      },
    ]),
    {
      confirm_apply: true,
      confirmations: [
        {
          document_id: "d1",
          extracted_field_id: "f1",
          decision: "CONFIRM",
          corrected_value: "120",
        },
        {
          document_id: "d2",
          extracted_field_id: "f2",
          decision: "REJECT",
          corrected_value: null,
        },
      ],
    },
  );
});

test("redacts credentials and storage internals recursively", () => {
  const { logic } = loadLogic();

  assert.deepEqual(
    logic.redactForLog({
      password: "secret",
      access_token: "jwt",
      object_key: "cases/a.pdf",
      nested: { bucket_name: "private", safe: "ok" },
    }),
    {
      password: "[REDACTED]",
      access_token: "[REDACTED]",
      object_key: "[REDACTED]",
      nested: { bucket_name: "[REDACTED]", safe: "ok" },
    },
  );
});

test("redacts the rendered request log, not only the helper output", async () => {
  const requestLog = fakeElement();
  const document = fakeDocument({ "request-log": requestLog });
  const { logic } = loadLogic({
    document,
    fetch: async () => ({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      async json() {
        return {
          password: "secret",
          object_key: "private/case.pdf",
          nested: { storage_url: "https://storage.invalid/file" },
        };
      },
    }),
  });

  await logic.request("/valuation/cases/case-1/auto-workflow/review");

  assert.match(requestLog.textContent, /\[REDACTED\]/);
  assert.doesNotMatch(requestLog.textContent, /secret|private\/case\.pdf|storage\.invalid/);
});

test("builds intake manifest from named controls rather than a JSON editor", () => {
  const { logic } = loadLogic();
  const form = fakeForm(
    {
      case_no: "CASE-001",
      case_title: "測試案件",
      case_type: "土地徵收補償市價查估",
      requesting_agency: "",
      valuation_base_date: "2026-09-05",
      city_code: "65000000",
      district_code: "65000010",
      land_use_type: "COMMERCIAL",
      parcel_section_name: "○○段",
      parcel_land_no: "0001-0000",
      parcel_area_sqm: "120.5",
      benchmark_land_no: "B-001",
      price_zone_no: "P-001",
      prepared_date: "2026-09-05",
      create_commercial_report: true,
      category_override: "land-register.pdf=land-register",
    },
    [{ name: "land-register.pdf" }],
  );

  assert.deepEqual(logic.buildIntakeManifest(form), {
    case: {
      case_no: "CASE-001",
      case_title: "測試案件",
      case_type: "土地徵收補償市價查估",
      requesting_agency: null,
      valuation_base_date: "2026-09-05",
      city_code: "65000000",
      district_code: "65000010",
      land_use_type: "COMMERCIAL",
    },
    parcels: [
      {
        district_code: "65000010",
        section_name: "○○段",
        subsection_name: "",
        land_no: "0001-0000",
        area_sqm: "120.5",
        land_use_zone: null,
        designated_use: null,
        ownership_numerator: null,
        ownership_denominator: null,
      },
    ],
    benchmark_lands: [
      {
        parcel_index: 0,
        benchmark_land_no: "B-001",
        price_zone_no: "P-001",
        land_consolidation_serial: null,
        latitude: null,
        longitude: null,
      },
    ],
    prepared_date: "2026-09-05",
    create_commercial_report: true,
    category_overrides: { "land-register.pdf": "land-register" },
  });
});

test("requires an explicit choice for every pending candidate", () => {
  const { logic } = loadLogic();
  const candidates = [
    { extracted_field_id: "f1", field_status: "NEEDS_CONFIRMATION" },
    { extracted_field_id: "f2", field_status: "NEEDS_CONFIRMATION" },
    { extracted_field_id: "f3", field_status: "CONFIRMED" },
  ];

  assert.equal(logic.canApplyCandidates(candidates, { f1: "CONFIRM" }), false);
  assert.equal(
    logic.canApplyCandidates(candidates, { f1: "CONFIRM", f2: "REJECT" }),
    true,
  );
});

test("uses selected case metadata and appends files without requiring it again", () => {
  const { logic } = loadLogic();
  logic.state.cases.push({
    case_id: "case-existing",
    case_no: "CASE-EXISTING",
    case_title: "既有案件",
    case_type: "土地徵收補償市價查估",
    requesting_agency: "測試機關",
    valuation_base_date: "2025-09-01",
    city_code: "65000000",
    district_code: "65000010",
    land_use_type: "COMMERCIAL",
  });
  const form = fakeForm({
    existing_case_id: "case-existing",
    category_override: "新文件.pdf=land-register",
    create_commercial_report: false,
  });

  assert.deepEqual(logic.buildIntakeManifest(form), {
    case: {
      case_no: "CASE-EXISTING",
      case_title: "既有案件",
      case_type: "土地徵收補償市價查估",
      requesting_agency: "測試機關",
      valuation_base_date: "2025-09-01",
      city_code: "65000000",
      district_code: "65000010",
      land_use_type: "COMMERCIAL",
    },
    parcels: [],
    benchmark_lands: [],
    prepared_date: null,
    create_commercial_report: true,
    category_overrides: { "新文件.pdf": "land-register" },
  });
});

test("requires one selected answer when a field has conflicting document candidates", () => {
  const { logic } = loadLogic();
  const candidates = [
    {
      extracted_field_id: "candidate-a",
      form_code: "F03",
      field_name: "benchmark_land_no",
      extracted_value: "P001-00",
      field_status: "NEEDS_CONFIRMATION",
    },
    {
      extracted_field_id: "candidate-b",
      form_code: "F03",
      field_name: "benchmark_land_no",
      extracted_value: "P002-00",
      field_status: "NEEDS_CONFIRMATION",
    },
  ];

  logic.saveWorkflow(candidateWorkflow({ candidates }));
  assert.equal(logic.candidateHasMultipleAnswers(candidates[0]), true);
  assert.equal(logic.canApplyCandidates(candidates, {
    "candidate-a": { choice: "CONFIRM" },
    "candidate-b": { choice: "CONFIRM" },
  }), false);
  assert.equal(logic.canApplyCandidates(candidates, {
    "candidate-a": { choice: "CONFIRM" },
    "candidate-b": { choice: "REJECT" },
  }), true);
});

test("formal workflow payloads require explicit confirmations", () => {
  const { logic } = loadLogic();

  assert.deepEqual(logic.formalCalculationPayload(true), {
    confirm_calculation: true,
  });
  assert.deepEqual(logic.formalReportPayload(true, ["WARN_MISSING_PHOTO"]), {
    confirm_generate: true,
    acknowledged_warning_codes: ["WARN_MISSING_PHOTO"],
  });
  assert.throws(() => logic.formalCalculationPayload(false), /確認/);
  assert.throws(() => logic.formalReportPayload(false, []), /確認/);
});

test("requires a successful formal validation before enabling final artifacts", () => {
  const { logic } = loadLogic();

  assert.equal(logic.hasSuccessfulFormalValidation(), false);
  assert.equal(logic.canSubmitForReview(), false);

  logic.state.formal.validation = {
    validation_run_id: "validation-1",
    can_generate_formal_report: false,
  };
  logic.state.formal.report = { document_id: "formal-pdf-1" };
  logic.state.formal.validation_run_id = "validation-1";
  assert.equal(logic.hasSuccessfulFormalValidation(), false);
  assert.equal(logic.canSubmitForReview(), false);

  logic.state.formal.validation.can_generate_formal_report = true;
  assert.equal(logic.hasSuccessfulFormalValidation(), true);
  assert.equal(logic.canSubmitForReview(), true);
});

test("builds submission command from current version and server IDs", () => {
  const { logic } = loadLogic();

  assert.deepEqual(
    logic.buildSubmitCommand(
      { version_no: 4 },
      { validation_run_id: "run-1" },
      { document_id: "document-1" },
      "request-1",
    ),
    {
      request_id: "request-1",
      expected_case_version: 4,
      source_validation_run_id: "run-1",
      source_report_document_id: "document-1",
    },
  );
});

test("labels candidate fields and workflow statuses for appraisers", () => {
  const { logic } = loadLogic();

  assert.equal(logic.fieldLabel("transaction_total_price"), "交易總價");
  assert.equal(logic.fieldLabel("unknown_field"), "待確認欄位");
  assert.equal(logic.codeLabel("UNKNOWN_WORKFLOW_CODE"), "系統檢核項目");
  assert.equal(logic.statusLabel("IN_REVIEW"), "審查中");
  assert.equal(logic.statusLabel("REVISION_REQUIRED"), "退回補正");
});

test("shows durable report progress instead of treating 製作中 as a finished report", () => {
  const { logic } = loadLogic();
  const baseProgress = {
    report_id: "report-1",
    sections: [
      { form_instance_id: "s01", status: "IN_PROGRESS" },
      { form_instance_id: "f02rf", status: "IN_PROGRESS" },
      { form_instance_id: "f02", status: "IN_PROGRESS" },
      { document_type: "map-section-sketch", status: "MISSING" },
      { document_type: "map-zoning", status: "MISSING" },
      { document_type: "map-land-value-section", status: "MISSING" },
    ],
  };

  const inProgress = logic.buildWorkflowProgress(baseProgress, { case_status: "PROCESSING" });
  assert.equal(inProgress.steps[0].complete, true);
  assert.equal(inProgress.steps[1].complete, false);
  assert.match(inProgress.summary, /尚未完成正式計算與檢核/);

  const complete = logic.buildWorkflowProgress(
    {
      ...baseProgress,
      sections: baseProgress.sections.map((section) => ({ ...section, status: "COMPLETED" })),
    },
    { case_status: "DRAFT" },
    { components: [{ form_status: "FINAL" }, { form_status: "FINAL" }, { form_status: "FINAL" }] },
  );
  assert.equal(complete.steps[3].complete, true);
  assert.match(complete.summary, /可以送出審查/);
});

test("keeps a correction typed after choosing confirmation", () => {
  const radio = fakeElement({ dataset: { choiceId: "f1" }, value: "CONFIRM" });
  const correction = fakeElement({ dataset: { correctedId: "f1" }, value: "" });
  const candidateList = fakeElement({
    querySelectorAll(selector) {
      if (selector.includes("data-choice-id")) return [radio];
      if (selector.includes("data-corrected-id")) return [correction];
      return [];
    },
    querySelector(selector) {
      return selector.includes('data-corrected-id="f1"') ? correction : null;
    },
  });
  const document = fakeDocument({
    "candidate-list": candidateList,
    "candidate-summary": fakeElement(),
    "candidate-action-message": fakeElement(),
    "confirm-candidates": fakeElement(),
  });
  const { logic } = loadLogic({ document });

  logic.saveWorkflow(candidateWorkflow());
  radio.getListener("change")();
  correction.value = "120";
  correction.getListener("input")();

  assert.deepEqual(logic.candidateRecordsFromState(), [{
    document_id: "d1",
    extracted_field_id: "f1",
    choice: "CONFIRM",
    corrected_value: "120",
  }]);
});

test("locks and unlocks candidate radios and correction fields with the case", () => {
  const radio = fakeElement({ dataset: { choiceId: "f1" } });
  const correction = fakeElement({ dataset: { correctedId: "f1" } });
  const controls = [radio, correction];
  const document = fakeDocument({}, (selector) => (
    selector.includes("#candidate-list") ? controls : []
  ));
  const { logic } = loadLogic({ document });

  logic.lockEditing(true);
  assert.equal(radio.disabled, true);
  assert.equal(correction.disabled, true);

  logic.lockEditing(false);
  assert.equal(radio.disabled, false);
  assert.equal(correction.disabled, false);
});

test("explains why formal calculation is unavailable", () => {
  const { logic } = loadLogic();

  assert.match(logic.formalActionReason(), /選擇案件/);

  logic.saveWorkflow(candidateWorkflow({ report_id: null }));
  assert.match(logic.formalActionReason(), /正式表單/);

  logic.lockEditing(true);
  assert.match(logic.formalActionReason(), /鎖定/);
});

test("clears a previous report id when workflow response has no report", () => {
  const { logic } = loadLogic();

  logic.saveWorkflow(candidateWorkflow({ report_id: "report-old" }));
  assert.equal(logic.state.report_id, "report-old");

  logic.saveWorkflow(candidateWorkflow({ report_id: null }));
  assert.equal(logic.state.report_id, null);
  assert.equal(logic.state.reportId, null);
});

test("uses the available pending candidate value as a display-only normalized value", () => {
  const { logic } = loadLogic();

  assert.equal(
    logic.candidateNormalizedValue({ extracted_value: " 120 ", confirmed_value: null }),
    "120",
  );
  assert.equal(
    logic.candidateNormalizedValue({ extracted_value: "raw", normalized_value: 120 }),
    120,
  );
});

test("does not generate a PDF when warning acknowledgement cannot be explicit", async () => {
  const calls = [];
  const { logic } = loadLogic({
    fetch: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith("/formal-calculation")) {
        return {
          ok: true,
          status: 200,
          headers: { get: () => "application/json" },
          async json() { return { calculation_id: "calc-1" }; },
        };
      }
      if (url.endsWith("/formal-validation")) {
        return {
          ok: true,
          status: 200,
          headers: { get: () => "application/json" },
          async json() {
            return {
              can_generate_formal_report: true,
              failed_count: 0,
              warning_count: 1,
              validation_run_id: "run-1",
              findings: [{ severity: "WARNING", code: "WARN_MISSING_PHOTO" }],
            };
          },
        };
      }
      if (url.endsWith("/reports/report-1")) {
        return jsonResponse({
          report_id: "report-1",
          components: [{ form_status: "CHECKED" }, { form_status: "CHECKED" }, { form_status: "CHECKED" }],
        });
      }
      if (url.endsWith("/report-progress")) {
        return jsonResponse({ report_id: "report-1", sections: [] });
      }
      throw new Error("formal PDF must not be requested");
    },
  });

  logic.saveWorkflow(candidateWorkflow({ candidates: [] }));
  const result = await logic.runFormalWorkflow();

  assert.equal(result.report, null);
  assert.equal(calls.length, 4);
  assert.ok(calls.every(({ url }) => !url.endsWith("/formal-pdf")));
});

test("revalidates checked or final forms without trying to calculate them again", async () => {
  const calls = [];
  const { logic } = loadLogic({
    fetch: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith("/formal-calculation")) throw new Error("calculation must be skipped");
      if (url.endsWith("/formal-validation")) {
        return jsonResponse({
          can_generate_formal_report: true,
          failed_count: 0,
          warning_count: 0,
          validation_run_id: "run-2",
          findings: [],
        });
      }
      if (url.endsWith("/formal-pdf")) {
        return jsonResponse({
          document_id: "formal-pdf-2",
          filename: "complete-report.pdf",
          version_no: 2,
          download_path: "/api/v1/valuation/cases/case-1/complete-reports/formal-pdf-2/download",
        });
      }
      if (url.endsWith("/reports/report-1")) {
        return jsonResponse({
          report_id: "report-1",
          components: [{ form_status: "FINAL" }, { form_status: "FINAL" }, { form_status: "FINAL" }],
        });
      }
      if (url.endsWith("/report-progress")) return jsonResponse({ report_id: "report-1", sections: [] });
      throw new Error(`unexpected request: ${url}`);
    },
  });

  logic.saveWorkflow(candidateWorkflow({ candidates: [] }));
  await logic.loadReportPackage();
  const result = await logic.runFormalWorkflow({ acknowledged_warning_codes: [] });

  assert.equal(result.report.document_id, "formal-pdf-2");
  assert.ok(calls.some(({ url }) => url.endsWith("/formal-validation")));
  assert.ok(calls.some(({ url }) => url.endsWith("/formal-pdf")));
  assert.ok(calls.every(({ url }) => !url.endsWith("/formal-calculation")));
});

test("logout clears case state, workflow IDs, and rendered panels", () => {
  const elements = casePanelElements();
  const { logic } = loadLogic({ document: fakeDocument(elements) });

  logic.saveWorkflow(candidateWorkflow({
    report_id: "old-report",
    candidates: [{
      extracted_field_id: "old-field",
      document_id: "old-document",
      field_name: "transaction_total_price",
      extracted_value: "999",
      field_status: "NEEDS_CONFIRMATION",
    }],
  }));
  logic.state.formal.validation = { validation_run_id: "old-run" };
  logic.state.formal.report = { document_id: "old-pdf", download_path: "/api/v1/valuation/old.pdf" };
  elements["formal-summary"].innerHTML = "舊正式報告";
  elements["formal-findings"].innerHTML = "舊檢核結果";
  elements["request-log"].textContent = "舊請求紀錄";
  elements["download-formal-report"].disabled = false;
  elements["refresh-candidates"].disabled = false;
  elements["run-formal-workflow"].disabled = false;

  logic.showLogin("已登出測試台。");

  assert.equal(logic.state.case, null);
  assert.equal(logic.state.selectedCaseId, null);
  assert.equal(logic.state.reportId, null);
  assert.deepEqual(logic.state.documents, []);
  assert.deepEqual(logic.state.candidates, []);
  assert.equal(logic.state.formal.validation, null);
  assert.equal(logic.state.formal.report, null);
  assert.equal(elements["candidate-list"].innerHTML, "");
  assert.match(elements["candidate-summary"].innerHTML, /目前尚無候選內容/);
  assert.match(elements["formal-summary"].innerHTML, /尚未產生/);
  assert.equal(elements["formal-findings"].innerHTML, "");
  assert.equal(elements["request-log"].textContent, "尚無請求紀錄。");
  assert.equal(elements["download-formal-report"].disabled, true);
  assert.equal(elements["refresh-candidates"].disabled, true);
  assert.equal(elements["run-formal-workflow"].disabled, true);
});

test("case replacement clears the old panels before the new review response arrives", async () => {
  const elements = casePanelElements();
  let resolveReview;
  const { logic } = loadLogic({
    document: fakeDocument(elements),
    fetch: async (url) => {
      if (url.endsWith("/auto-workflow/review")) {
        return new Promise((resolve) => { resolveReview = resolve; });
      }
      if (url.endsWith("/review-handoff")) return jsonResponse({ case_status: "DRAFT" });
      throw new Error(`unexpected request: ${url}`);
    },
  });

  logic.saveWorkflow(candidateWorkflow());
  assert.match(elements["candidate-list"].innerHTML, /交易總價/);

  const loading = logic.loadCase("case-2");
  assert.equal(elements["candidate-list"].innerHTML, "");
  assert.equal(elements["download-formal-report"].disabled, true);
  assert.equal(logic.state.reportId, null);

  resolveReview(jsonResponse(candidateWorkflow({
    case: { case_id: "case-2", case_title: "新案件" },
    report_id: null,
    candidates: [],
  })));
  await loading;
  assert.equal(logic.state.selectedCaseId, "case-2");
});

test("ignores a case response that finishes after logout", async () => {
  const elements = casePanelElements();
  let resolveReview;
  const { logic } = loadLogic({
    document: fakeDocument(elements),
    fetch: async (url) => {
      if (url.endsWith("/auto-workflow/review")) {
        return new Promise((resolve) => { resolveReview = resolve; });
      }
      throw new Error(`unexpected request: ${url}`);
    },
  });

  logic.saveWorkflow(candidateWorkflow({ report_id: "old-report" }));
  const loading = logic.loadCase("case-2");
  logic.showLogin("已登出測試台。");

  resolveReview(jsonResponse(candidateWorkflow({
    case: { case_id: "case-2", case_title: "不應重新顯示的案件" },
    report_id: null,
    candidates: [{
      extracted_field_id: "stale-field",
      document_id: "stale-document",
      field_name: "transaction_total_price",
      extracted_value: "999",
      field_status: "NEEDS_CONFIRMATION",
    }],
  })));
  await loading;

  assert.equal(logic.state.case, null);
  assert.equal(logic.state.selectedCaseId, null);
  assert.equal(logic.state.reportId, null);
  assert.deepEqual(logic.state.candidates, []);
  assert.equal(elements["candidate-list"].innerHTML, "");
  assert.equal(elements["request-log"].textContent, "尚無請求紀錄。");
});

test("ignores a failed case response that finishes after logout", async () => {
  const elements = casePanelElements();
  const caseSelector = fakeElement({ value: "case-2" });
  elements["case-selector"] = caseSelector;
  let resolveReview;
  const { logic } = loadLogic({
    document: fakeDocument(elements),
    fetch: async (url) => {
      if (url.endsWith("/auto-workflow/review")) {
        return new Promise((resolve) => { resolveReview = resolve; });
      }
      throw new Error(`unexpected request: ${url}`);
    },
  });

  logic.saveWorkflow(candidateWorkflow());
  caseSelector.getListener("change")({ target: caseSelector });
  logic.showLogin("已登出測試台。");

  resolveReview(jsonResponse({ message: "舊使用者未授權" }, 401));
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(elements["status-message"].textContent, "已登出測試台。");
  assert.equal(logic.state.case, null);
  assert.equal(logic.state.selectedCaseId, null);
  assert.equal(elements["request-log"].textContent, "尚無請求紀錄。");
});

test("new intake clears the old case before the intake response arrives", async () => {
  const elements = casePanelElements();
  let resolveIntake;
  class FakeFormData {
    constructor() { this.entries = []; }
    append(...entry) { this.entries.push(entry); }
  }
  const { logic } = loadLogic({
   document: fakeDocument(elements),
   FormData: FakeFormData,
   fetch: async (url) => {
      if (url.endsWith("/auto-workflows/intake")) {
        return new Promise((resolve) => { resolveIntake = resolve; });
      }
      if (url.endsWith("/valuation/cases")) return jsonResponse([{ case_id: "new-case", case_no: "NEW-001", case_title: "新收件案件" }]);
      throw new Error(`unexpected request: ${url}`);
    },
  });

  logic.saveWorkflow(candidateWorkflow());
  const form = fakeForm(
    { case_no: "NEW-001", case_title: "新收件案件" },
    [{ name: "source.pdf" }],
  );
  const submitting = logic.submitIntake({ form });

  assert.equal(elements["candidate-list"].innerHTML, "");
  assert.equal(logic.state.reportId, null);
  assert.equal(elements["download-formal-report"].disabled, true);

  resolveIntake(jsonResponse(candidateWorkflow({
    case: { case_id: "new-case", case_title: "新收件案件" },
    report_id: null,
    candidates: [],
  })));
  await submitting;
  assert.equal(logic.state.selectedCaseId, "new-case");
});

test("ignores a new-intake response that finishes after logout", async () => {
  const elements = casePanelElements();
  let resolveIntake;
  class FakeFormData {
    append() {}
  }
  const { logic } = loadLogic({
    document: fakeDocument(elements),
    FormData: FakeFormData,
    fetch: async (url) => {
      if (url.endsWith("/auto-workflows/intake")) {
        return new Promise((resolve) => { resolveIntake = resolve; });
      }
      if (url.endsWith("/valuation/cases")) return jsonResponse([]);
      throw new Error(`unexpected request: ${url}`);
    },
  });

  logic.saveWorkflow(candidateWorkflow({ report_id: "old-report" }));
  const submitting = logic.submitIntake({
    form: fakeForm(
      { case_no: "NEW-001", case_title: "不應重新顯示的新案件" },
      [{ name: "source.pdf" }],
    ),
  });
  logic.showLogin("已登出測試台。");

  resolveIntake(jsonResponse(candidateWorkflow({
    case: { case_id: "stale-new-case", case_title: "不應重新顯示的新案件" },
    report_id: null,
    candidates: [],
  })));
  await submitting;

  assert.equal(logic.state.case, null);
  assert.equal(logic.state.selectedCaseId, null);
  assert.equal(logic.state.reportId, null);
  assert.deepEqual(logic.state.documents, []);
  assert.equal(elements["candidate-list"].innerHTML, "");
  assert.equal(elements["request-log"].textContent, "尚無請求紀錄。");
});

test("unknown labels keep escaped machine identity as secondary detail", () => {
  const elements = casePanelElements();
  const { logic } = loadLogic({ document: fakeDocument(elements) });

  logic.saveWorkflow(candidateWorkflow({
    candidates: [{
      extracted_field_id: "f-unknown",
      document_id: "d1",
      field_name: "<unmapped-field>",
      extracted_value: "value",
      field_status: "NEEDS_CONFIRMATION",
    }],
    warnings: ["<UNKNOWN_BLOCKER>"],
  }));

  assert.match(elements["candidate-list"].innerHTML, /待確認欄位/);
  assert.match(elements["candidate-list"].innerHTML, /欄位代碼：&lt;unmapped-field&gt;/);
  assert.doesNotMatch(elements["candidate-list"].innerHTML, /<h3>&lt;unmapped-field&gt;/);
  assert.match(elements["status-message"].innerHTML, /系統檢核項目/);
  assert.match(elements["status-message"].innerHTML, /檢核代碼：&lt;UNKNOWN_BLOCKER&gt;/);
});

test("treats inherited identifiers as unknown labels with escaped detail", () => {
  const elements = casePanelElements();
  const { logic } = loadLogic({ document: fakeDocument(elements) });

  logic.saveWorkflow(candidateWorkflow({
    candidates: [{
      extracted_field_id: "f-inherited",
      document_id: "d1",
      field_name: "constructor",
      extracted_value: "value",
      field_status: "NEEDS_CONFIRMATION",
    }],
    warnings: ["toString"],
  }));

  assert.match(elements["candidate-list"].innerHTML, /待確認欄位/);
  assert.match(elements["candidate-list"].innerHTML, /欄位代碼：constructor/);
  assert.match(elements["status-message"].innerHTML, /系統檢核項目/);
  assert.match(elements["status-message"].innerHTML, /檢核代碼：toString/);
});

test("uses Chinese labels for candidate fields in every supported form", () => {
  const { logic } = loadLogic();

  assert.equal(logic.candidateFieldLabel("F01", "transaction_total_price"), "交易總價（元）");
  assert.equal(logic.candidateFieldLabel("F02", "target_1_trial_price"), "比較標的－試算價格（元／㎡）");
  assert.equal(logic.candidateFieldLabel("F03", "benchmark_land_price"), "比準地地價（元／㎡）");
  assert.equal(logic.candidateFieldLabel("F04", "parcel_2_parcel_total_value"), "宗地－宗地總價（元）");
  assert.equal(logic.candidateFieldLabel("F02-RF", "urban_plan_status"), "都市計畫（內、外）");
  assert.equal(logic.candidateFieldLabel("S01", "zone_boundary_description"), "區段範圍");
});

test("renders a Chinese report type label in the report selector", async () => {
  const elements = casePanelElements();
  const { logic } = loadLogic({
    document: fakeDocument(elements),
    fetch: async () => jsonResponse({ report_type: "REPORT_COMPARISON_COMMERCIAL" }),
  });

  logic.saveWorkflow(candidateWorkflow({ candidates: [] }));
  await logic.loadReportPackage();

  assert.match(elements["form-selector"].innerHTML, /商業用地比較報告/);
  assert.doesNotMatch(elements["form-selector"].innerHTML, />REPORT_COMPARISON_COMMERCIAL<\/option>/);
});

test("request prefixes API paths, sends JSON, and attaches the bearer token", async () => {
  const calls = [];
  const { logic } = loadLogic({
    fetch: async (url, options) => {
      calls.push({ url, options });
      return {
        ok: true,
        status: 200,
        headers: { get: () => "application/json" },
        async json() {
          return { ok: true };
        },
      };
    },
  });
  logic.setToken("jwt-secret");

  const result = await logic.request("/auth/me", {
    method: "POST",
    body: { sample: "value" },
  });

  assert.deepEqual(result, { ok: true });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/auth/me");
  assert.equal(calls[0].options.headers.Authorization, "Bearer jwt-secret");
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
  assert.equal(calls[0].options.body, JSON.stringify({ sample: "value" }));
});

test("request turns a non-success response into a UI error", async () => {
  const { logic } = loadLogic({
    fetch: async () => ({
      ok: false,
      status: 422,
      headers: { get: () => "application/json" },
      async json() {
        return { message: "資料格式錯誤", password: "hidden" };
      },
    }),
  });

  await assert.rejects(
    logic.request("/valuation/auto-workflows/intake", { method: "POST", body: {} }),
    (error) => error.status === 422 && error.message === "資料格式錯誤",
  );
});

test("the testable state view never exposes the bearer token", () => {
  const { logic } = loadLogic();
  logic.setToken("jwt-secret");
  assert.equal(logic.state.token, "[REDACTED]");
});
