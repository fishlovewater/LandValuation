"""Deterministic development data for manually testing Case-history.

Run inside the API runtime with ``python -m app.history.demo seed|status|reset``.
"""

import argparse
import asyncio
import hashlib
import os
from io import BytesIO
from pathlib import Path
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _load_dotenv() -> None:
    path = Path.cwd() / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()
if os.getenv("POSTGRES_HOST"):
    # Compose explicitly supplies POSTGRES_HOST=db. Prefer these component
    # variables over a mounted .env DATABASE_URL that points at localhost.
    DATABASE_URL = (
        "postgresql+psycopg://"
        f"{os.getenv('POSTGRES_USER', 'app_user')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'change_me')}@"
        f"{os.getenv('POSTGRES_HOST')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'land_valuation')}"
    )
else:
    DATABASE_URL = os.getenv("DATABASE_URL") or (
        "postgresql+psycopg://app_user:change_me@localhost:5432/land_valuation"
    )
engine = None
SessionFactory = None


def _database_runtime():
    global engine, SessionFactory
    if engine is not None:
        return engine, SessionFactory
    try:
        engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "History demo requires a working psycopg driver (for example "
            "psycopg[binary]); run it in the complete API runtime/container"
        ) from exc
    SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, SessionFactory


def _minio_client():
    try:
        from minio import Minio
    except ImportError as exc:
        raise RuntimeError(
            "seed requires the project's 'minio' package; install project "
            "requirements or run this command inside the API container"
        ) from exc
    access_key = os.getenv("MINIO_ACCESS_KEY") or os.getenv("MINIO_ROOT_USER")
    secret_key = os.getenv("MINIO_SECRET_KEY") or os.getenv("MINIO_ROOT_PASSWORD")
    if not access_key or not secret_key:
        raise RuntimeError("MINIO access key/secret are missing from environment or .env")
    return Minio(
        os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=access_key,
        secret_key=secret_key,
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )


def _bucket() -> str:
    return os.getenv("MINIO_BUCKET", "land-valuation")


def _ensure_development() -> None:
    if os.getenv("APP_ENV", "").lower() != "development":
        raise RuntimeError(
            "DEVELOPMENT_ONLY: demo commands require APP_ENV=development"
        )


VALUATION_CASE_ID = UUID("71000000-0000-4000-8000-000000000001")
REVIEW_CASE_ID = UUID("71000000-0000-4000-8000-000000000002")
BOTH_CASE_ID = UUID("71000000-0000-4000-8000-000000000003")
CASE_IDS = (VALUATION_CASE_ID, REVIEW_CASE_ID, BOTH_CASE_ID)
PARCEL_ID = UUID("72000000-0000-4000-8000-000000000001")
FORM_ID = UUID("73000000-0000-4000-8000-000000000001")
VALUATION_ID = UUID("74000000-0000-4000-8000-000000000001")
REVIEW_ID = UUID("75000000-0000-4000-8000-000000000001")
BOTH_REVIEW_ID = UUID("75000000-0000-4000-8000-000000000002")
REVIEW_IDS = (REVIEW_ID, BOTH_REVIEW_ID)
RISK_ID = UUID("76000000-0000-4000-8000-000000000001")
DOWNLOAD_DOCUMENT_ID = UUID("77000000-0000-4000-8000-000000000001")
MISSING_DOCUMENT_ID = UUID("77000000-0000-4000-8000-000000000002")
DOCUMENT_IDS = (DOWNLOAD_DOCUMENT_ID, MISSING_DOCUMENT_ID)
DOWNLOAD_OBJECT_KEY = f"cases/{BOTH_CASE_ID}/generated/{DOWNLOAD_DOCUMENT_ID}/v1/history-demo-report.pdf"
MISSING_OBJECT_KEY = f"cases/{REVIEW_CASE_ID}/generated/{MISSING_DOCUMENT_ID}/v1/history-demo-missing.docx"

APPRAISER_USER_ID = UUID("78000000-0000-4000-8000-000000000001")
REVIEWER_USER_ID = UUID("78000000-0000-4000-8000-000000000002")
USER_IDS = (APPRAISER_USER_ID, REVIEWER_USER_ID)
DEMO_PASSWORD = "HistoryDemo123!"
DEMO_USERS = (
    {
        "user_id": APPRAISER_USER_ID,
        "username": "history_appraiser",
        "email": "history_appraiser@example.test",
        "display_name": "History 測試估價人員",
        "role_code": "APPRAISER",
    },
    {
        "user_id": REVIEWER_USER_ID,
        "username": "history_reviewer",
        "email": "history_reviewer@example.test",
        "display_name": "History 測試審查人員",
        "role_code": "REVIEWER",
    },
)

PDF_BYTES = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 57>>stream
BT /F1 16 Tf 30 80 Td (Case-history demo download) Tj ET
endstream endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f\x20
0000000009 00000 n\x20
0000000058 00000 n\x20
0000000115 00000 n\x20
0000000241 00000 n\x20
0000000347 00000 n\x20
trailer<</Size 6/Root 1 0 R>>
startxref
417
%%EOF
"""


async def _delete_rows(session) -> None:
    await session.execute(text("DELETE FROM review.risk_summaries WHERE review_id=:id"), {"id": REVIEW_ID})
    await session.execute(
        text("DELETE FROM review.reviews WHERE review_id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ),
        {"ids": REVIEW_IDS},
    )
    await session.execute(text("DELETE FROM valuation.valuations WHERE valuation_id=:id"), {"id": VALUATION_ID})
    await session.execute(text("DELETE FROM valuation.form_instances WHERE form_instance_id=:id"), {"id": FORM_ID})
    await session.execute(text("DELETE FROM valuation.parcels WHERE parcel_id=:id"), {"id": PARCEL_ID})
    await session.execute(
        text("DELETE FROM valuation.documents WHERE document_id IN :ids").bindparams(bindparam("ids", expanding=True)),
        {"ids": DOCUMENT_IDS},
    )
    await session.execute(
        text("DELETE FROM valuation.cases WHERE case_id IN :ids").bindparams(bindparam("ids", expanding=True)),
        {"ids": CASE_IDS},
    )
    await session.execute(
        text("DELETE FROM auth.user_roles WHERE user_id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ),
        {"ids": USER_IDS},
    )
    await session.execute(
        text("DELETE FROM auth.users WHERE user_id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ),
        {"ids": USER_IDS},
    )


async def reset() -> None:
    _ensure_development()
    _, sessions = _database_runtime()
    async with sessions() as session:
        async with session.begin():
            await _delete_rows(session)
    client = _minio_client()
    await asyncio.to_thread(client.remove_object, _bucket(), DOWNLOAD_OBJECT_KEY)


async def seed() -> None:
    _ensure_development()
    # Lazy import keeps ``status``/``reset`` usable in a partial local Python
    # environment; password hashing is required only while creating accounts.
    from app.core.security import hash_password

    client = _minio_client()  # Validate dependency and credentials before mutation.
    bucket = _bucket()
    if not await asyncio.to_thread(client.bucket_exists, bucket):
        raise RuntimeError(f"MinIO bucket does not exist: {bucket}")
    await reset()
    uploaded = await asyncio.to_thread(
        client.put_object,
        bucket,
        DOWNLOAD_OBJECT_KEY,
        BytesIO(PDF_BYTES),
        len(PDF_BYTES),
        content_type="application/pdf",
    )
    try:
        _, sessions = _database_runtime()
        async with sessions() as session:
            async with session.begin():
                for demo_user in DEMO_USERS:
                    role_exists = await session.scalar(
                        text("""SELECT EXISTS (
                            SELECT 1 FROM auth.roles
                            WHERE role_code=:role_code AND is_active=true
                        )"""),
                        {"role_code": demo_user["role_code"]},
                    )
                    if not role_exists:
                        raise RuntimeError(
                            f"{demo_user['role_code']}_ROLE_MISSING: run migrations before seed"
                        )
                    await session.execute(text("""INSERT INTO auth.users
                        (user_id,username,email,password_hash,display_name,is_active,created_at,updated_at)
                        VALUES (:user_id,:username,:email,:password_hash,:display_name,true,now(),now())"""), {
                        **demo_user,
                        "password_hash": hash_password(DEMO_PASSWORD),
                    })
                    await session.execute(text("""INSERT INTO auth.user_roles (user_id,role_id)
                        SELECT :user_id,role_id FROM auth.roles
                        WHERE role_code=:role_code AND is_active=true"""), demo_user)
                await session.execute(text("""INSERT INTO valuation.cases
                    (case_id,case_no,case_title,case_type,valuation_base_date,city_code,district_code,land_use_type,case_status)
                    VALUES
                    (:v,'HIST-VAL-001','History 測試－只有估價結構化資料','LAND',DATE '2026-08-01','31','3101','COMMERCIAL','CORRECTION'),
                    (:r,'HIST-REV-001','History 測試－Review metadata 但 MinIO 缺檔','LAND',DATE '2026-08-02','31','3102','RESIDENTIAL','REVIEWING'),
                    (:b,'HIST-BOTH-001','History 測試－雙子系統及可下載文件','LAND',DATE '2026-08-03','31','3104','COMMERCIAL','COMPLETED')"""),
                    {"v": VALUATION_CASE_ID, "r": REVIEW_CASE_ID, "b": BOTH_CASE_ID})
                await session.execute(text("""INSERT INTO valuation.parcels
                    (parcel_id,case_id,district_code,section_name,subsection_name,land_no,area_sqm)
                    VALUES (:id,:case_id,'3101','測試段','','123-4',168.5)"""),
                    {"id": PARCEL_ID, "case_id": VALUATION_CASE_ID})
                await session.execute(text("""INSERT INTO valuation.form_instances
                    (form_instance_id,case_id,form_code,version_no,form_status)
                    VALUES (:id,:case_id,'F01',1,'FINAL')"""),
                    {"id": FORM_ID, "case_id": VALUATION_CASE_ID})
                await session.execute(text("""INSERT INTO valuation.valuations
                    (valuation_id,case_id,form_instance_id,valuation_type,unit_price,total_value,calculation_snapshot,result_status)
                    VALUES (:id,:case_id,:form_id,'CASE',88000,14828000,CAST(:snapshot AS jsonb),'FINAL')"""),
                    {"id": VALUATION_ID, "case_id": VALUATION_CASE_ID, "form_id": FORM_ID,
                     "snapshot": '{"demo":true,"method":"comparison","unit_price":88000}'})
                await session.execute(text("""INSERT INTO review.reviews
                    (review_id,case_id,review_type,review_status,received_at,started_at,completed_at)
                    VALUES (:id,:case_id,'SMART_REVIEW','COMPLETED',
                    TIMESTAMPTZ '2026-08-19 09:00:00+08',
                    TIMESTAMPTZ '2026-08-20 10:00:00+08',
                    TIMESTAMPTZ '2026-08-20 12:00:00+08'),
                    (:both_id,:both_case,'MANUAL_REVIEW','RUNNING',
                    TIMESTAMPTZ '2026-08-20 09:00:00+08',
                    TIMESTAMPTZ '2026-08-21 10:00:00+08',NULL)"""),
                    {"id": REVIEW_ID, "case_id": REVIEW_CASE_ID,
                     "both_id": BOTH_REVIEW_ID, "both_case": BOTH_CASE_ID})
                await session.execute(text("""INSERT INTO review.risk_summaries
                    (risk_summary_id,review_id,overall_risk_level,risk_score,summary,category_scores)
                    VALUES (:id,:review_id,'LOW',12.5,'History demo：低風險測試資料',
                    CAST(:category_scores AS jsonb))"""),
                    {"id": RISK_ID, "review_id": REVIEW_ID,
                     "category_scores": '{"completeness":95}'})
                await session.execute(text("""INSERT INTO valuation.documents
                    (document_id,document_group_id,case_id,document_type,original_filename,mime_type,
                     bucket_name,object_key,checksum_sha256,file_size_bytes,version_no,is_active,storage_etag)
                    VALUES
                    (:did,:did,:both,'generated-report','history-demo-report.pdf','application/pdf',
                     :bucket,:dkey,:dhash,:dsize,1,true,:etag),
                    (:mid,:mid,:review,'review-report','history-demo-missing.docx',
                     'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                     :bucket,:mkey,:mhash,128,1,true,NULL)"""), {
                    "did": DOWNLOAD_DOCUMENT_ID, "both": BOTH_CASE_ID,
                    "mid": MISSING_DOCUMENT_ID, "review": REVIEW_CASE_ID,
                    "bucket": bucket, "dkey": DOWNLOAD_OBJECT_KEY,
                    "dhash": hashlib.sha256(PDF_BYTES).hexdigest(), "dsize": len(PDF_BYTES),
                    "etag": uploaded.etag, "mkey": MISSING_OBJECT_KEY,
                    "mhash": hashlib.sha256(b"missing-demo-object").hexdigest(),
                })
    except Exception:
        await asyncio.to_thread(client.remove_object, bucket, DOWNLOAD_OBJECT_KEY)
        raise


async def status() -> None:
    _, sessions = _database_runtime()
    async with sessions() as session:
        rows = (await session.execute(
            text("""SELECT c.case_id,c.case_no,c.case_title,count(d.document_id) document_count
                    FROM valuation.cases c LEFT JOIN valuation.documents d ON d.case_id=c.case_id
                    WHERE c.case_id IN :ids GROUP BY c.case_id,c.case_no,c.case_title ORDER BY c.case_no""").bindparams(bindparam("ids", expanding=True)),
            {"ids": CASE_IDS})).mappings().all()
        users = (await session.execute(
            text("""SELECT u.username,u.display_name,r.role_code,u.is_active
                    FROM auth.users u
                    JOIN auth.user_roles ur ON ur.user_id=u.user_id
                    JOIN auth.roles r ON r.role_id=ur.role_id
                    WHERE u.user_id IN :ids ORDER BY u.username""").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": USER_IDS},
        )).mappings().all()
    print(*(dict(row) for row in rows), sep="\n")
    print(*(dict(user) for user in users), sep="\n")
    if not rows and not users:
        print("History demo data is not seeded.")


async def main(command: str) -> None:
    try:
        await {"seed": seed, "status": status, "reset": reset}[command]()
    finally:
        if engine is not None:
            await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Case-history demo data")
    parser.add_argument("command", choices=("seed", "status", "reset"))
    asyncio.run(main(parser.parse_args().command))
