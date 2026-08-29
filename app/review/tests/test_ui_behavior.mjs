import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const html = readFileSync(
  new URL("../test_ui/index.html", import.meta.url),
  "utf8",
);
const startMarker = "// TESTABLE_WORKBENCH_LOGIC_START";
const endMarker = "// TESTABLE_WORKBENCH_LOGIC_END";
const start = html.indexOf(startMarker);
const end = html.indexOf(endMarker);

assert.notEqual(start, -1, "testable workbench logic start marker is missing");
assert.notEqual(end, -1, "testable workbench logic end marker is missing");

const source = html.slice(start + startMarker.length, end);
const scriptSource = html.match(/<script>([\s\S]*)<\/script>/)?.[1] ?? "";
const logic = new Function(
  `${source}; return { redactForLog, findingDecisionBody, validateFindingDecision, startOutcomeMessage, workbenchCasesPath, copyDemoCommand, documentTypeLabel, findingDecisionLabel, caseDecisionLabel, findingStatusLabel, severityLabel, flattenDisplayData, requiresAfterValue, documentContentPath, pdfPageTarget, requestLogSummary };`,
)();

test("inline workbench script parses", () => {
  assert.doesNotThrow(() => new Function(scriptSource));
});

test("request logs recursively redact credentials", () => {
  assert.deepEqual(
    logic.redactForLog({
      access_token: "secret",
      nested: { password: "secret", ordinary: "visible" },
    }),
    {
      access_token: "[REDACTED]",
      nested: { password: "[REDACTED]", ordinary: "visible" },
    },
  );
});

test("partial acceptance sends a formal after value", () => {
  assert.deepEqual(
    logic.findingDecisionBody(
      "review-1",
      { field_path: "comparables[0].adjustment_rate" },
      "PARTIALLY_ACCEPTED",
      "採納修正值",
      "-7",
    ),
    {
      review_id: "review-1",
      decision: "PARTIALLY_ACCEPTED",
      reason: "採納修正值",
      after_value: {
        field_path: "comparables[0].adjustment_rate",
        value: "-7",
      },
    },
  );
  assert.throws(
    () =>
      logic.findingDecisionBody(
        "review-1",
        { field_path: null },
        "PARTIALLY_ACCEPTED",
        "採納修正值",
        "",
      ),
    /正式值/,
  );
});

test("blocked review is announced as an error", () => {
  assert.deepEqual(
    logic.startOutcomeMessage({
      outcome: "BLOCKED",
      completeness: { items: [{ item_name: "土地登記謄本" }] },
    }),
    { message: "智慧審查暫停：土地登記謄本。", error: true },
  );
});

test("case queue request preserves server-side group pagination and filters", () => {
  assert.equal(
    logic.workbenchCasesPath({
      limit: 25,
      offset: 25,
      group: "completed",
      q: "板橋 A",
      risk: "HIGH",
    }),
    "/review/workbench/cases?limit=25&offset=25&status_group=completed&q=%E6%9D%BF%E6%A9%8B%20A&risk_level=HIGH",
  );
});

test("demo seed command is copied with visible success feedback", async () => {
  let copied = "";
  const result = await logic.copyDemoCommand(async (value) => {
    copied = value;
  });

  assert.equal(
    copied,
    "rtk docker exec land_valuation_api python -m app.review.demo seed",
  );
  assert.deepEqual(result, {
    message: "指令已複製，請貼到 PowerShell 執行。",
    error: false,
  });
});

test("clipboard failure keeps a manual-copy fallback", async () => {
  const result = await logic.copyDemoCommand(async () => {
    throw new Error("denied");
  });

  assert.deepEqual(result, {
    message: "無法自動複製，請手動選取上方指令。",
    error: true,
  });
});

test("review codes have Chinese display labels", () => {
  assert.equal(logic.documentTypeLabel("cadastral-map"), "地籍圖");
  assert.equal(logic.documentTypeLabel("land-register"), "土地登記謄本");
  assert.equal(logic.findingDecisionLabel("PARTIALLY_ACCEPTED"), "部分採納");
  assert.equal(logic.caseDecisionLabel("APPROVED"), "核定通過");
  assert.equal(logic.documentTypeLabel("custom"), "其他文件（custom）");
});

test("structured evidence becomes readable rows instead of JSON", () => {
  assert.deepEqual(
    logic.flattenDisplayData([
      { document_version: 2, page_number: 3, verification_status: "VERIFIED" },
    ]),
    [
      { label: "法規文件版本", value: "2" },
      { label: "頁碼", value: "3" },
      { label: "確認狀態", value: "已確認" },
    ],
  );
});

test("finding cards use Chinese decision and risk labels", () => {
  assert.equal(logic.findingStatusLabel("OPEN"), "待決策");
  assert.equal(logic.findingStatusLabel("ACCEPTED"), "已決策：採納疑點");
  assert.equal(
    logic.findingStatusLabel("EXPERT_REVIEW"),
    "專業覆核（既有資料）",
  );
  assert.equal(logic.severityLabel("HIGH"), "高風險");
  assert.equal(logic.severityLabel("MEDIUM"), "中風險");
});

test("review evidence hides trace keys and localizes legal fields", () => {
  assert.deepEqual(
    logic.flattenDisplayData([
      {
        rule_name: "調整率一致性檢核",
        version_name: "2026 年正式版",
        version_no: 3,
        effective_from: "2026-01-01",
        effective_to: null,
        bounding_box: { left: 0.1 },
        checksum_sha256: "a".repeat(64),
        rule_version_id: "technical-id",
        source_id: "source-id",
      },
    ]),
    [
      { label: "規則名稱", value: "調整率一致性檢核" },
      { label: "規則版本", value: "2026 年正式版" },
      { label: "版次", value: "3" },
      { label: "生效日期", value: "2026-01-01" },
      { label: "有效截止日", value: "持續有效" },
    ],
  );
});

test("only partial acceptance requires an after value", () => {
  assert.equal(logic.requiresAfterValue("PARTIALLY_ACCEPTED"), true);
  assert.equal(logic.requiresAfterValue("ACCEPTED"), false);
});

test("document preview path is review scoped and page aware", () => {
  assert.equal(
    logic.documentContentPath("review-1", "document-2"),
    "/review/workbench/cases/review-1/documents/document-2/content",
  );
  assert.equal(logic.pdfPageTarget("blob:preview", 7), "blob:preview#page=7");
  assert.equal(logic.pdfPageTarget("blob:preview", null), "blob:preview#page=1");
});

test("request log summary keeps request identity while collapsed", () => {
  assert.equal(
    logic.requestLogSummary("GET", "/review/workbench/summary", 200, 42),
    "GET /review/workbench/summary · 200 · 42 ms",
  );
});
