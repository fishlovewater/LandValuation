"""Create an explicitly labelled Demo case and exercise the public API end to end."""
from io import BytesIO
import json
from pathlib import Path

import httpx
from openpyxl import Workbook


def main():
    with httpx.Client(base_url="http://127.0.0.1:18000/api/v1", timeout=90) as client:
        def call(method, path, **kwargs):
            result = client.request(method, path, **kwargs)
            if result.is_error:
                raise RuntimeError(f"{method} {path}: {result.status_code} {result.text[:800]}")
            return result.json()

        login = call("POST", "/auth/demo-login", json={"role": "REVIEWER"})
        client.headers["Authorization"] = "Bearer " + login["access_token"]
        case = call("POST", "/review/workbench/external-cases", json={
            "case_title": "Demo OCR 自動填表流程驗證（模擬資料）", "district_code": "65000010",
            "source_organization": "Demo 模擬文件", "valuation_base_date": "2026-09-13"})
        base = f"/review/workbench/cases/{case['review_id']}"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "比較標的1"
        for row in [("實例編號", "DEMO-AUTO-001"), ("面積", "123.25"), ("交易總價", "1000000"),
                    ("行政區", "板橋區"), ("段", "文化段"), ("地號", "123-1")]:
            sheet.append(row)
        stream = BytesIO()
        workbook.save(stream)
        document = call("POST", base + "/external-documents", data={"category": "original"},
                        files={"file": ("Demo-auto-fill.xlsx", stream.getvalue(),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        doc = base + f"/external-documents/{document['document_id']}"
        extracted = call("POST", doc + "/extract")
        automatic = [field for field in extracted["candidates"] if field["field_status"] == "AUTO_APPLIED"]
        pending = [field for field in extracted["candidates"] if field["field_status"] == "NEEDS_CONFIRMATION"]
        assert automatic and pending, extracted
        assert all(field["confirmed_by_user_id"] is None for field in automatic)
        assert client.post(base + "/start/preflight").status_code == 409

        def confirm_pending(result):
            pending_fields = [field for field in result["candidates"] if field["field_status"] == "NEEDS_CONFIRMATION"]
            if pending_fields:
                return call("POST", doc + "/extraction/confirm", json={"confirmations": [
                    {"extracted_field_id": field["extracted_field_id"], "decision": "CONFIRM"}
                    for field in pending_fields]})
            return result

        confirmed = confirm_pending(extracted)
        area = next(field for field in confirmed["candidates"] if field["field_name"] == "land_area")
        call("POST", doc + "/extraction/confirm", json={"confirmations": [{
            "extracted_field_id": area["extracted_field_id"], "decision": "CONFIRM", "corrected_value": "124"}]})
        forms_before = call("GET", doc + "/forms")
        assert any(field["value"] == "124" for form in forms_before for field in form["fields"])
        repeated = call("POST", doc + "/extract")
        assert repeated["extraction_id"] != extracted["extraction_id"]
        confirm_pending(repeated)
        forms_after = call("GET", doc + "/forms")
        assert forms_after[0]["form_instance_id"] != forms_before[0]["form_instance_id"]
        assert any(field["value"] == "123.25" for form in forms_after for field in form["fields"])
        run = call("POST", base + "/start")
        assert run["outcome"] == "COMPLETED", run
        assert run["completeness"]["missing_item_count"] == 3
        assert "Demo" in run["risk_summary"]["summary"]
        call("POST", f"/review/cases/{case['review_id']}/complete-review",
             json={"reason": "驗證 Demo 自動填表與缺件放行；本案為模擬資料。"})
        report = call("POST", f"/review/runs/{run['run']['validation_run_id']}/reports", json={"format": "PDF"})
        result = {"case": case, "automatic_fields": len(automatic), "human_fields": len(pending),
                  "new_extraction_verified": True, "missing_materials": 3,
                  "review_completed": True, "report": report}
        output = Path(__file__).resolve().parents[1] / "output/review-auto-smoke.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"case_no": case["case_no"], "review_id": case["review_id"],
                          "automatic": len(automatic), "human": len(pending), "completed": True}))


if __name__ == "__main__":
    main()
