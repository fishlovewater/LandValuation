import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionFactory, dispose_engine
from app.valuation.models import (
    CaseRecord,
    FormInstanceRecord,
    AssistantSessionRecord,
    DocumentRecord,
    ExtractedFieldRecord,
    BenchmarkLandRecord,
    RuleVersionRecord,
)

async def main():
    async with AsyncSessionFactory() as session:
        # Get latest case
        case_stmt = select(CaseRecord).order_by(CaseRecord.created_at.desc()).limit(1)
        case_result = await session.execute(case_stmt)
        case = case_result.scalar_one_or_none()
        
        if not case:
            print("\n[提示] 資料庫中目前沒有任何估價案件 (Case)。請先建立案件。")
            await dispose_engine()
            return
            
        print("\n==================================================")
        print("   當前最新估價案件 UUID 資訊 (可直接複製使用)")
        print("==================================================")
        print(f"案件名稱: {case.case_title} ({case.case_no})")
        print(f"土地用途: {case.land_use_type}")
        print(f"👉 case_id:\n   {case.case_id}\n")

        # Get latest published rule version
        rule_stmt = (
            select(RuleVersionRecord)
            .where(RuleVersionRecord.status == "PUBLISHED")
            .order_by(RuleVersionRecord.created_at.desc())
            .limit(1)
        )
        rule_result = await session.execute(rule_stmt)
        rule = rule_result.scalar_one_or_none()
        if rule:
            print(f"適用規則包: {rule.version_name} ({rule.jurisdiction_code})")
            print(f"👉 rule_version_id:\n   {rule.rule_version_id}\n")
        else:
            print("適用規則包: [無] (請先匯入並發布規則包)\n")

        # Get latest benchmark land for this case
        bench_stmt = (
            select(BenchmarkLandRecord)
            .where(BenchmarkLandRecord.case_id == case.case_id)
            .order_by(BenchmarkLandRecord.created_at.desc())
            .limit(1)
        )
        bench_result = await session.execute(bench_stmt)
        bench = bench_result.scalar_one_or_none()
        if bench:
            print(f"比準地代號: {bench.benchmark_land_no}")
            print(f"👉 benchmark_land_id:\n   {bench.benchmark_land_id}\n")

        # Get latest form instance for this case
        form_stmt = (
            select(FormInstanceRecord)
            .where(FormInstanceRecord.case_id == case.case_id)
            .order_by(FormInstanceRecord.created_at.desc())
            .limit(1)
        )
        form_result = await session.execute(form_stmt)
        form = form_result.scalar_one_or_none()
        if form:
            print(f"最新表單: {form.form_code} (Status: {form.form_status})")
            print(f"👉 form_instance_id:\n   {form.form_instance_id}\n")
        else:
            print("最新表單: [無] (請先為此案件建立表單實例，例如 F03)\n")

        # Get latest F02 (Report Package Root) form instance for this case
        f02_stmt = (
            select(FormInstanceRecord)
            .where(FormInstanceRecord.case_id == case.case_id, FormInstanceRecord.form_code == "F02")
            .order_by(FormInstanceRecord.created_at.desc())
            .limit(1)
        )
        f02_result = await session.execute(f02_stmt)
        f02_form = f02_result.scalar_one_or_none()
        if f02_form:
            print(f"最新報告書套件 (F02):")
            print(f"👉 report_id:\n   {f02_form.form_instance_id}\n")
        else:
            print("最新報告書套件 (F02): [無] (請先建立報告書套件以取得 report_id)\n")

        # Get latest assistant session for this case
        session_stmt = (
            select(AssistantSessionRecord)
            .where(AssistantSessionRecord.case_id == case.case_id)
            .order_by(AssistantSessionRecord.created_at.desc())
            .limit(1)
        )
        session_result = await session.execute(session_stmt)
        assistant_session = session_result.scalar_one_or_none()
        if assistant_session:
            print(f"最新對話 Session ID (Status: {assistant_session.session_status})")
            print(f"👉 assistant_session_id:\n   {assistant_session.assistant_session_id}\n")
        else:
            print("最新對話 Session: [無] (請先為此案件啟動對話工作階段)\n")

        # Get latest uploaded document for this case
        doc_stmt = (
            select(DocumentRecord)
            .where(DocumentRecord.case_id == case.case_id)
            .order_by(DocumentRecord.uploaded_at.desc())
            .limit(1)
        )
        doc_result = await session.execute(doc_stmt)
        doc = doc_result.scalar_one_or_none()
        if doc:
            print(f"最新文件: {doc.original_filename} ({doc.document_type})")
            print(f"👉 document_id:\n   {doc.document_id}\n")
        else:
            print("最新文件: [無]\n")

        # Get latest extracted fields for this case
        fields_stmt = (
            select(ExtractedFieldRecord)
            .where(ExtractedFieldRecord.case_id == case.case_id)
            .order_by(ExtractedFieldRecord.field_name.asc())
        )
        fields_result = await session.execute(fields_stmt)
        fields = fields_result.scalars().all()
        if fields:
            print("最新提取欄位候選值 (用於確認與修改):")
            for field in fields:
                print(f"🔹 欄位: {field.field_name} (Status: {field.field_status})")
                print(f"   提取值: {field.extracted_value}")
                print(f"   👉 關聯 document_id: {field.document_id}")
                print(f"   👉 extracted_field_id:\n      {field.extracted_field_id}\n")
        else:
            print("最新提取欄位: [無] (請先執行 OCR 擷取與模型分析)\n")

        print("==================================================")

    await dispose_engine()

if __name__ == "__main__":
    import selectors
    import sys
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    else:
        asyncio.run(main())
