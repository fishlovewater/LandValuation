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
  `${source}; return { redactForLog, findingTriageBody, validateFindingTriage, startOutcomeMessage, workbenchCasesPath, copyDemoCommand, documentTypeLabel, findingDecisionLabel, caseDecisionLabel, findingStatusLabel, severityLabel, flattenDisplayData, documentContentPath, pdfPageTarget, requestLogSummary, findingActionLabel, latestFindingDecision, correctionBlockers, completionBlockers, activeCorrectionRequest, recheckDisplayRequest, canRegisterResubmission, canRecheck, isCorrectionReadOnly, canExportCorrectionNotice, canExportFinalReport, correctionRequestBody, correctionStatusLabel, recheckOutcomeLabel, urgencyLabel, urgencyBadgeText, riskBadgeText, isLegacyDecision, reviewProgress, executeReviewWorkflow, createDraftTracker, confirmDiscardChanges, applyBeforeUnload, canStartReview };`,
)();

test("inline workbench script parses", () => {
  assert.doesNotThrow(() => new Function(scriptSource));
});

test("reviewer report UI excludes raw structured-report rendering", () => {
  assert.doesNotMatch(html, /預覽 JSON/);
  assert.doesNotMatch(html, /data-report-json/);
  assert.doesNotMatch(html, /id="report-preview"/);
  assert.doesNotMatch(html, /button\.hasAttribute\("data-report-json"\)/);
  assert.doesNotMatch(
    html,
    /JSON\.stringify\(await request\(`\/review\/runs\/\$\{latest\.validation_run_id\}\/report`\)/,
  );
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

test("custom final content sends only the reviewer value", () => {
  assert.deepEqual(
    logic.findingTriageBody("review-1", "CONFIRMED_ISSUE", " 與適用規則不一致 "),
    {
      review_id: "review-1",
      decision: "CONFIRMED_ISSUE",
      reason: "與適用規則不一致",
    },
  );
  // A triage body must never carry a reviewer-selected formal value.
  assert.equal(
    "after_value" in
      logic.findingTriageBody("review-1", "CONFIRMED_ISSUE", "理由"),
    false,
  );
  assert.throws(
    () => logic.findingTriageBody("review-1", "CONFIRMED_ISSUE", "   "),
    /判定理由/,
  );
  for (const legacy of ["ACCEPTED", "REJECTED", "PARTIALLY_ACCEPTED"]) {
    assert.throws(
      () => logic.findingTriageBody("review-1", legacy, "理由"),
      /人工判定結果/,
    );
  }
});

test("triage validation returns field-specific Chinese errors", () => {
  assert.deepEqual(logic.validateFindingTriage("CONFIRMED_ISSUE", ""), {
    reason: "請填寫判定理由。",
  });
  assert.deepEqual(logic.validateFindingTriage("PARTIALLY_ACCEPTED", "理由"), {
    decision: "請選擇人工判定結果。",
  });
  assert.deepEqual(
    logic.validateFindingTriage("DISMISSED_FALSE_POSITIVE", "屬誤判"),
    {},
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

test("review progress uses only completed workflow milestones", () => {
  assert.deepEqual(logic.reviewProgress("PREPARING"), {
    value: 0,
    label: "準備檢核",
  });
  assert.deepEqual(logic.reviewProgress("COMPLETENESS"), {
    value: 25,
    label: "完整性檢查完成",
  });
  assert.equal(logic.reviewProgress("RULES").value, 75);
  assert.equal(logic.reviewProgress("DETAIL").value, 90);
  assert.equal(logic.reviewProgress("COMPLETE").value, 100);
  assert.throws(() => logic.reviewProgress("UNKNOWN"), /未知的檢核進度/);
});

test("blocked review stops after completeness without creating a run", async () => {
  const calls = [];
  const result = await logic.executeReviewWorkflow({
    onProgress: (stage) => calls.push(`progress:${stage}`),
    preflight: async () => {
      calls.push("preflight");
      return { outcome: "BLOCKED", completeness: { items: [] } };
    },
    run: async () => calls.push("run"),
    loadDetail: async () => calls.push("detail"),
    loadSummary: async () => calls.push("summary"),
  });

  assert.equal(result.outcome, "BLOCKED");
  assert.deepEqual(calls, [
    "progress:PREPARING",
    "preflight",
    "progress:COMPLETENESS",
    "detail",
    "summary",
  ]);
});

test("ready review advances only after each real operation completes", async () => {
  const calls = [];
  await logic.executeReviewWorkflow({
    onProgress: (stage) => calls.push(`progress:${stage}`),
    preflight: async () => {
      calls.push("preflight");
      return { outcome: "READY" };
    },
    run: async () => calls.push("run"),
    loadDetail: async () => calls.push("detail"),
    loadSummary: async () => calls.push("summary"),
  });

  assert.deepEqual(calls, [
    "progress:PREPARING",
    "preflight",
    "progress:COMPLETENESS",
    "run",
    "progress:RULES",
    "detail",
    "progress:DETAIL",
    "summary",
    "progress:COMPLETE",
  ]);
});

test("review workflow locks editing until every operation settles", async () => {
  let releasePreflight;
  const locks = [];
  const pending = new Promise((resolve) => {
    releasePreflight = resolve;
  });
  const workflow = logic.executeReviewWorkflow({
    setLocked: (locked) => locks.push(locked),
    onProgress: () => {},
    preflight: () => pending,
    run: async () => {},
    loadDetail: async () => {},
    loadSummary: async () => {},
  });

  await Promise.resolve();
  assert.deepEqual(locks, [true]);
  releasePreflight({ outcome: "BLOCKED" });
  await workflow;
  assert.deepEqual(locks, [true, false]);
});

test("failed run keeps the last completed milestone and unlocks editing", async () => {
  const stages = [];
  const locks = [];
  await assert.rejects(
    logic.executeReviewWorkflow({
      setLocked: (locked) => locks.push(locked),
      onProgress: (stage) => stages.push(stage),
      preflight: async () => ({ outcome: "READY" }),
      run: async () => {
        throw new Error("run failed");
      },
      loadDetail: async () => {},
      loadSummary: async () => {},
    }),
    /run failed/,
  );
  assert.deepEqual(stages, ["PREPARING", "COMPLETENESS"]);
  assert.deepEqual(locks, [true, false]);
});

test("ready review remains runnable after a failed first run or rerun", () => {
  assert.equal(
    logic.canStartReview({ review: { review_status: "READY_FOR_REVIEW" }, runs: [] }),
    true,
  );
  assert.equal(
    logic.canStartReview({
      review: { review_status: "READY_FOR_REVIEW" },
      runs: [{ run_no: 1 }],
    }),
    true,
  );
});

test("draft tracker becomes clean again when values return to baseline", () => {
  const drafts = logic.createDraftTracker();
  const initial = { decision: "REJECTED", reason: "", afterValue: "" };
  drafts.register("finding:f-1", initial);

  drafts.update("finding:f-1", { ...initial, reason: "待確認" });
  assert.equal(drafts.isDirty("finding:f-1"), true);
  assert.equal(drafts.hasAny(), true);

  drafts.update("finding:f-1", initial);
  assert.equal(drafts.isDirty("finding:f-1"), false);
  assert.equal(drafts.hasAny(), false);
});

test("draft tracker isolates findings and clears only a successful save", () => {
  const drafts = logic.createDraftTracker();
  const initial = { decision: "REJECTED", reason: "", afterValue: "" };
  drafts.register("finding:f-1", initial);
  drafts.register("finding:f-2", initial);
  drafts.update("finding:f-1", { ...initial, reason: "第一筆" });
  drafts.update("finding:f-2", { ...initial, reason: "第二筆" });

  drafts.clear("finding:f-1");

  assert.equal(drafts.isDirty("finding:f-1"), false);
  assert.equal(drafts.isDirty("finding:f-2"), true);
  assert.deepEqual(drafts.value("finding:f-2"), {
    ...initial,
    reason: "第二筆",
  });
  assert.equal(drafts.hasAny(), true);
});

test("discard confirmation runs only for dirty drafts", () => {
  const drafts = logic.createDraftTracker();
  let asked = 0;
  assert.equal(
    logic.confirmDiscardChanges(drafts, () => {
      asked += 1;
      return false;
    }),
    true,
  );
  assert.equal(asked, 0);

  drafts.register("case:r-1", { reason: "" });
  drafts.update("case:r-1", { reason: "待確認" });
  assert.equal(logic.confirmDiscardChanges(drafts, () => false), false);
  assert.equal(drafts.hasAny(), true);
  assert.equal(logic.confirmDiscardChanges(drafts, () => true), true);
  assert.equal(drafts.hasAny(), false);
});

test("beforeunload is blocked only while drafts are dirty", () => {
  const drafts = logic.createDraftTracker();
  const cleanEvent = { prevented: false, preventDefault() { this.prevented = true; } };
  assert.equal(logic.applyBeforeUnload(cleanEvent, drafts), false);
  assert.equal(cleanEvent.prevented, false);

  drafts.register("finding:f-1", { reason: "" });
  drafts.update("finding:f-1", { reason: "尚未儲存" });
  const dirtyEvent = { prevented: false, returnValue: null, preventDefault() { this.prevented = true; } };
  assert.equal(logic.applyBeforeUnload(dirtyEvent, drafts), true);
  assert.equal(dirtyEvent.prevented, true);
  assert.equal(dirtyEvent.returnValue, "");
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
  assert.equal(logic.documentTypeLabel("custom"), "其他文件（custom）");
  assert.equal(logic.findingDecisionLabel("CONFIRMED_ISSUE"), "確認有問題");
  assert.equal(
    logic.findingDecisionLabel("DISMISSED_FALSE_POSITIVE"),
    "排除誤判",
  );
  assert.equal(logic.findingDecisionLabel("EXPERT_REVIEW"), "轉專業覆核");
  assert.equal(logic.caseDecisionLabel("APPROVED"), "確認無誤並完成審查");
  assert.equal(logic.caseDecisionLabel("RETURNED_FOR_REVISION"), "送出修正通知");
});

test("legacy stored decisions are labelled as history, not as new actions", () => {
  for (const legacy of [
    "ACCEPTED",
    "REJECTED",
    "PARTIALLY_ACCEPTED",
    "REQUIRES_SUPPLEMENT",
  ]) {
    assert.equal(logic.isLegacyDecision(legacy), true);
    assert.match(logic.findingDecisionLabel(legacy), /舊流程歷史決策/);
  }
  assert.equal(logic.isLegacyDecision("CONFIRMED_ISSUE"), false);
  assert.doesNotMatch(
    logic.findingDecisionLabel("CONFIRMED_ISSUE"),
    /舊流程歷史決策/,
  );
});

test("correction and recheck states have Chinese labels", () => {
  assert.equal(logic.correctionStatusLabel("SENT"), "已送出，等待修正版");
  assert.equal(logic.correctionStatusLabel("RECHECKED"), "重檢完成");
  assert.equal(logic.recheckOutcomeLabel("RESOLVED"), "已解決");
  assert.equal(logic.recheckOutcomeLabel("STILL_PRESENT"), "仍存在");
  assert.equal(logic.recheckOutcomeLabel("NOT_EVALUATED"), "無法判定");
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

test("finding cards use Chinese triage and risk labels", () => {
  assert.equal(logic.findingStatusLabel("OPEN"), "尚未判定");
  assert.equal(
    logic.findingStatusLabel("CONFIRMED_ISSUE"),
    "已判定：確認有問題",
  );
  assert.equal(
    logic.findingStatusLabel("DISMISSED_FALSE_POSITIVE"),
    "已判定：排除誤判",
  );
  assert.match(logic.findingStatusLabel("PARTIALLY_ACCEPTED"), /舊流程歷史決策/);
  assert.equal(logic.severityLabel("HIGH"), "高風險");
  assert.equal(logic.severityLabel("MEDIUM"), "中風險");
});

test("risk and deadline urgency use separate wording", () => {
  assert.equal(logic.riskBadgeText("HIGH"), "高風險");
  assert.equal(logic.riskBadgeText(null), "尚未評級");
  assert.equal(logic.urgencyBadgeText("URGENT", 2), "剩 2 天・緊急");
  assert.equal(logic.urgencyBadgeText("DUE_SOON", 6), "剩 6 天・即將到期");
  assert.equal(logic.urgencyBadgeText("OVERDUE", -1), "已逾期・已逾期");
  assert.equal(logic.urgencyBadgeText("NOT_SET", null), "期限未設定");
  // A deadline label must never read as a content-risk label.
  assert.notEqual(logic.urgencyBadgeText("URGENT", 2), logic.riskBadgeText("HIGH"));
});

test("finding action reflects whether a triage exists", () => {
  assert.equal(logic.findingActionLabel("OPEN"), "開始判定");
  assert.equal(logic.findingActionLabel("CONFIRMED_ISSUE"), "查看判定");
  assert.equal(logic.findingActionLabel("DISMISSED_FALSE_POSITIVE"), "查看判定");
});

test("latest finding decision is selected by timestamp", () => {
  const latest = logic.latestFindingDecision(
    [
      { finding_id: "f-1", reason: "第一次", decided_at: "2026-01-01T00:00:00Z" },
      { finding_id: "f-2", reason: "別筆", decided_at: "2026-01-03T00:00:00Z" },
      { finding_id: "f-1", reason: "第二次", decided_at: "2026-01-02T00:00:00Z" },
    ],
    "f-1",
  );
  assert.equal(latest.reason, "第二次");
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

test("correction blockers require a fully triaged run with a confirmed issue", () => {
  assert.deepEqual(
    logic.correctionBlockers({
      runs: [{ run_status: "COMPLETED" }],
      findings: [{ finding_id: "f-1", status: "OPEN" }],
      correction_requests: [],
    }),
    ["尚有 1 項疑點未判定", "沒有確認成立的疑點"],
  );
  assert.deepEqual(
    logic.correctionBlockers({
      runs: [{ run_status: "COMPLETED" }],
      findings: [{ finding_id: "f-1", status: "EXPERT_REVIEW" }],
      correction_requests: [],
    }),
    ["尚有 1 項專業覆核", "沒有確認成立的疑點"],
  );
  assert.deepEqual(
    logic.correctionBlockers({
      runs: [{ run_status: "COMPLETED" }],
      findings: [{ finding_id: "f-1", status: "CONFIRMED_ISSUE" }],
      correction_requests: [],
    }),
    [],
  );
  assert.deepEqual(
    logic.correctionBlockers({
      runs: [{ run_status: "COMPLETED" }],
      findings: [{ finding_id: "f-1", status: "CONFIRMED_ISSUE" }],
      correction_requests: [{ status: "SENT" }],
    }),
    ["已有未完成修正通知"],
  );
});

test("completion blockers cover every unfinished condition", () => {
  const clean = {
    review: { review_status: "REVIEW_REQUIRED" },
    runs: [{ run_status: "COMPLETED" }],
    missing_items: [],
    findings: [{ finding_id: "f-1", status: "DISMISSED_FALSE_POSITIVE" }],
    correction_requests: [],
  };
  assert.deepEqual(logic.completionBlockers(clean), []);
  assert.deepEqual(
    logic.completionBlockers({ ...clean, missing_items: [{}] }),
    ["仍有 1 項缺件"],
  );
  assert.deepEqual(
    logic.completionBlockers({
      ...clean,
      findings: [{ finding_id: "f-1", status: "CONFIRMED_ISSUE" }],
    }),
    ["仍有 1 項疑點待修正"],
  );
  assert.deepEqual(
    logic.completionBlockers({
      ...clean,
      correction_requests: [{ status: "SENT", items: [] }],
    }),
    ["仍有修正通知尚未完成新版重檢"],
  );
  assert.deepEqual(
    logic.completionBlockers({
      ...clean,
      correction_requests: [
        { status: "RECHECKED", items: [{ recheck_outcome: "NOT_EVALUATED" }] },
      ],
    }),
    ["仍有修正項目無法判定重檢結果"],
  );
});

test("correction lifecycle gates match the server state machine", () => {
  const sent = { status: "SENT" };
  const resubmitted = { status: "RESUBMITTED" };
  const rechecked = { status: "RECHECKED" };
  assert.equal(logic.canRegisterResubmission(sent), true);
  assert.equal(logic.canRegisterResubmission(resubmitted), false);
  assert.equal(logic.canRecheck(resubmitted), true);
  assert.equal(logic.canRecheck(sent), false);
  // While waiting for a revised version the case stays read-only.
  assert.equal(logic.isCorrectionReadOnly(sent), true);
  assert.equal(logic.isCorrectionReadOnly({ status: "DRAFT" }), false);
  assert.equal(logic.isCorrectionReadOnly(rechecked), false);
  assert.equal(logic.canExportCorrectionNotice({ status: "DRAFT" }), false);
  assert.equal(logic.canExportCorrectionNotice(sent), true);
  assert.equal(logic.canExportCorrectionNotice(rechecked), true);
  assert.equal(
    logic.activeCorrectionRequest({
      correction_requests: [{ status: "RECHECKED" }, { status: "SENT" }],
    }).status,
    "SENT",
  );
  assert.equal(
    logic.activeCorrectionRequest({ correction_requests: [{ status: "RECHECKED" }] }),
    null,
  );
  assert.equal(
    logic.recheckDisplayRequest({
      correction_requests: [
        { request_no: 1, status: "RECHECKED" },
        { request_no: 2, status: "SENT" },
      ],
    }).request_no,
    2,
  );
  assert.equal(
    logic.recheckDisplayRequest({
      correction_requests: [{ request_no: 1, status: "RECHECKED" }],
    }).request_no,
    1,
  );
});

test("final report export is only offered after the review completes", () => {
  assert.equal(
    logic.canExportFinalReport({ review: { review_status: "REVIEW_COMPLETED" } }),
    true,
  );
  assert.equal(
    logic.canExportFinalReport({ review: { review_status: "REVIEW_REQUIRED" } }),
    false,
  );
});

test("correction request body requires a message and a deadline", () => {
  assert.deepEqual(
    logic.correctionRequestBody(" 請更正 ", "2026-09-05T10:00"),
    { message: "請更正", due_at: new Date("2026-09-05T10:00").toISOString() },
  );
  assert.throws(() => logic.correctionRequestBody("  ", "2026-09-05T10:00"), /修正通知內容/);
  assert.throws(() => logic.correctionRequestBody("請更正", ""), /修正期限/);
});

test("completion is a single final action without legacy value choices", () => {
  assert.match(html, />確認無誤並完成審查</);
  assert.doesNotMatch(html, /<option value="REVIEW_COMPLETED">/);
  assert.doesNotMatch(html, /<option value="APPROVED">/);
  for (const forbidden of [
    "本項最後採用哪個內容",
    "維持原申報內容<\\/option>",
    "採用系統建議內容<\\/option>",
    "另訂正式內容<\\/option>",
  ]) {
    assert.doesNotMatch(html, new RegExp(forbidden));
  }
  assert.doesNotMatch(html, /data-finding-after-value/);
  assert.doesNotMatch(html, /data-partial-value-box/);
  assert.doesNotMatch(html, /after_value/);
});

test("the four business tabs are present", () => {
  for (const tab of ["檢核結果", "修正通知", "新版重檢", "報告與歷程"]) {
    assert.match(html, new RegExp(tab));
  }
  assert.match(html, /匯出 Excel/);
  assert.match(html, /匯出 Word/);
  assert.match(html, /建立修正通知單/);
});

test("irreversible actions are confirmed with plain wording", () => {
  assert.match(html, /完成後案件即結案且不可再變更，確定送出？/);
  assert.match(
    html,
    /送出後修正通知內容即固定，且案件將轉為退回修正，確定送出？/,
  );
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
