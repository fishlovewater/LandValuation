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
      throw new Error("formal PDF must not be requested");
    },
  });

  logic.saveWorkflow(candidateWorkflow({ candidates: [] }));
  const result = await logic.runFormalWorkflow();

  assert.equal(result.report, null);
  assert.equal(calls.length, 2);
  assert.ok(calls.every(({ url }) => !url.endsWith("/formal-pdf")));
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
