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
const logic = new Function(
  `${source}; return { redactForLog, findingDecisionBody, startOutcomeMessage, workbenchCasesPath, copyDemoCommand, documentTypeLabel, findingDecisionLabel, caseDecisionLabel, flattenDisplayData, requiresAfterValue };`,
)();

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
      { label: "文件版本", value: "2" },
      { label: "頁碼", value: "3" },
      { label: "確認狀態", value: "已確認" },
    ],
  );
});

test("only partial acceptance requires an after value", () => {
  assert.equal(logic.requiresAfterValue("PARTIALLY_ACCEPTED"), true);
  assert.equal(logic.requiresAfterValue("ACCEPTED"), false);
});
