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
  `${source}; return { redactForLog, findingDecisionBody, startOutcomeMessage, workbenchCasesPath };`,
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
