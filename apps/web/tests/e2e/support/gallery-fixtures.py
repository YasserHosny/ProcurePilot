"""PPS-36 hosted-only fixture, reserved exclusively to slug landing-gallery-demo.

Auth provisioning follows the hosted integration suite's Supabase admin path; login and
browser reads use the real JWT/RLS API. All connections use procurepilot_api.db.connect.
The general seed.py is deliberately NEVER called: it can mutate an unrelated first tenant.
`--pdf INDEX` is offline and writes a valid, deterministic source PDF as base64.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import UUID, uuid5

import arabic_reshaper
from bidi.algorithm import get_display
from dotenv import dotenv_values
from gotrue.errors import AuthApiError
from procurepilot_api import db
from procurepilot_api.modules.billing.service import assign_default_plan_in_signup
from procurepilot_api.modules.landed_cost.rules import (
    LandedCostInputs,
    MoneyValue,
    compute_landed_cost,
)
from procurepilot_api.modules.offers.basket_service import _job
from procurepilot_api.modules.savings.baseline import (
    CALCULATION_VERSION,
    capture_baseline,
)
from procurepilot_api.modules.savings.schemas import Money
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from supabase import create_client

ROOT = Path(__file__).resolve().parents[5]
AT = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
NAMESPACE = UUID("f2afaaab-1586-40c7-a466-6a7d8e132036")
SLUG = "landing-gallery-demo"
TENANT_ID = uuid5(NAMESPACE, f"tenant:{SLUG}")
AUTH_USER_ID = uuid5(NAMESPACE, f"auth-owner:{SLUG}")
OWNER_EMAIL = "nour.hassan@landing-gallery-demo.example.test"
TENANT_NAME = (
    "Fennel Courtyard · Synthetic demonstration data | فناء الشمر · بيانات اصطناعية"
)
POOLER_HOST = "aws-1-eu-west-1.pooler.supabase.com"
FILENAMES = [
    "cumin-grove-foods.pdf",
    "anise-harbour-supply.pdf",
    "sumac-garden-provisions.pdf",
]
SUPPLIERS = [
    "Cumin Grove Foods | أغذية بستان الكمون",
    "Anise Harbour Supply | تموين مرفأ اليانسون",
    "Sumac Garden Provisions | مؤن حديقة السماق",
]
PRODUCTS = ["Egyptian white rice | أرز مصري أبيض", "Red lentils | عدس أحمر"]
# Per supplier: (kg per pack, EGP per pack). Different packs, same base-unit products.
PACKS = [[(25, 1000), (10, 700)], [(10, 440), (20, 1200)], [(5, 230), (5, 325)]]
DELIVERY = [40, 50, 60]


def ident(key: str) -> UUID:
    return uuid5(TENANT_ID, key)


class FixtureRefused(RuntimeError):
    """Only constant, credential-free messages from this class may reach the CLI."""


def hosted_environment() -> dict[str, str]:
    """Offline guard. Read secrets locally; never print them or put them in CLI arguments.

    .env may contain a transaction-pooler DSN; only the constructed session-mode DSN
    (5432) can reach db.connect. A shell override must identify the same project/database.
    """
    if os.environ.get("CAPTURE_LANDING_GALLERY") != "1":
        raise FixtureRefused(
            "CAPTURE_LANDING_GALLERY=1 is required for hosted fixture operations"
        )
    if os.environ.get("CI"):
        raise FixtureRefused(
            "Hosted gallery captures run on a developer machine, never in CI"
        )
    if not (ROOT / ".env").is_file():
        raise FixtureRefused(
            "The untracked repo-root .env is required for hosted gallery captures"
        )
    values = {
        key: value for key, value in dotenv_values(ROOT / ".env").items() if value
    }
    configured = urlparse(values.get("DATABASE_URL", ""))
    candidate = urlparse(
        os.environ.get("DATABASE_URL") or values.get("DATABASE_URL", "")
    )
    for parsed in (configured, candidate):
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"} or parsed.port in {
            54321,
            54322,
        }:
            raise FixtureRefused("Local Supabase is forbidden for landing captures")
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or parsed.hostname != POOLER_HOST
        ):
            raise FixtureRefused(
                "DATABASE_URL must use the hosted demo pooler configured in .env"
            )
        if parsed.port not in {5432, 6543}:
            raise FixtureRefused(
                "The hosted pooler must have a recognised session/transaction port"
            )
    if (candidate.username, candidate.hostname, candidate.path) != (
        configured.username,
        configured.hostname,
        configured.path,
    ):
        raise FixtureRefused(
            "DATABASE_URL override does not identify the .env demo database"
        )
    user_info, _, _ = candidate.netloc.rpartition("@")
    session_url = candidate._replace(netloc=f"{user_info}@{POOLER_HOST}:5432").geturl()
    params = conninfo_to_dict(session_url)
    if (
        params.get("host") != POOLER_HOST
        or params.get("port") != "5432"
        or "hostaddr" in params
    ):
        raise FixtureRefused(
            "Connection parameters attempted to override the session pooler"
        )
    if (params.get("user"), params.get("dbname")) != (
        unquote(configured.username or ""),
        unquote(configured.path.removeprefix("/")),
    ):
        raise FixtureRefused(
            "Connection parameters attempted to override the demo project/database"
        )
    if set(params) - {
        "host",
        "port",
        "dbname",
        "user",
        "password",
        "sslmode",
        "connect_timeout",
        "application_name",
    }:
        raise FixtureRefused("Unsupported connection overrides in DATABASE_URL")
    supabase = urlparse(values.get("SUPABASE_URL", ""))
    project = (configured.username or "").removeprefix("postgres.")
    if (
        supabase.scheme != "https"
        or supabase.hostname != f"{project}.supabase.co"
        or supabase.port not in {None, 443}
        or supabase.path not in {"", "/"}
        or supabase.query
        or supabase.fragment
        or supabase.username
        or supabase.password
    ):
        raise FixtureRefused(
            "SUPABASE_URL and the .env pooler must identify the same hosted project"
        )
    if not values.get("SUPABASE_SERVICE_ROLE_KEY"):
        raise FixtureRefused(
            "SUPABASE_SERVICE_ROLE_KEY is required in the untracked repo .env"
        )
    return {
        **values,
        "DATABASE_URL": session_url,
        "SUPABASE_URL": supabase.geturl().rstrip("/"),
    }


def owned_tenant(
    conn: object, *, allow_missing: bool = False
) -> dict[str, object] | None:
    row = conn.execute(
        "select id, name, currency, platform_invitation_id from tenant where slug = %s",
        (SLUG,),
    ).fetchone()
    if row is None and allow_missing:
        return None
    # This name is a refusal guard only; never search for or access that curated workspace.
    if row is None or row["name"] == "مطاعم سند":
        raise FixtureRefused(
            "The reserved gallery slug is missing or belongs to a protected tenant"
        )
    if row["id"] != TENANT_ID or row["name"] != TENANT_NAME or row["currency"] != "EGP":
        raise FixtureRefused("The reserved gallery slug is not owned by this fixture")
    return row


def bootstrap(payload: dict[str, object]) -> dict[str, object]:
    env = hosted_environment()  # Must complete before any SQL or admin request.
    password = payload.get("password")
    if not isinstance(password, str) or len(password) < 32:
        raise FixtureRefused("A runtime-generated owner password is required on stdin")
    with db.connect(
        env["DATABASE_URL"], row_factory=dict_row, sslmode="require", connect_timeout=20
    ) as conn:
        conn.execute("reset role")
        conn.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (SLUG,))
        tenant = owned_tenant(conn, allow_missing=True)
        admin = create_client(
            env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"]
        ).auth.admin
        try:
            user = admin.get_user_by_id(str(AUTH_USER_ID)).user
        except AuthApiError as error:
            if error.status != 404:
                raise
            user = None
        if user is not None:
            if (
                user.email != OWNER_EMAIL
                or user.app_metadata.get("gallery_fixture") != SLUG
            ):
                raise FixtureRefused(
                    "The reserved auth identity is not owned by the gallery fixture"
                )
            admin.update_user_by_id(str(AUTH_USER_ID), {"password": password})
        else:
            user = admin.create_user(
                {
                    "id": str(AUTH_USER_ID),
                    "email": OWNER_EMAIL,
                    "password": password,
                    "email_confirm": True,
                    "app_metadata": {"gallery_fixture": SLUG},
                }
            ).user
        if user is None or UUID(user.id) != AUTH_USER_ID:
            raise FixtureRefused(
                "The admin path did not provision the reserved gallery owner"
            )
        if tenant is None:
            invitation = ident("platform-invitation")
            # One already-spent bootstrap invitation, never a usable published invitation token.
            conn.execute(
                "insert into platform_invitation (id,email,token_hash,expires_at,status,spent_at,created_at) "
                "values (%s,%s,%s,%s,'spent',%s,%s)",
                (
                    invitation,
                    OWNER_EMAIL,
                    hashlib.sha256(str(invitation).encode()).hexdigest(),
                    AT,
                    AT,
                    AT,
                ),
            )
            conn.execute(
                "insert into tenant (id,name,slug,region,currency,tax_model,default_locale,platform_invitation_id) "
                "values (%s,%s,%s,'EG','EGP','eg_vat_standard','en',%s)",
                (TENANT_ID, TENANT_NAME, SLUG, invitation),
            )
        member_id = ident("owner-membership")
        conn.execute(
            "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace,status,preferred_locale) "
            "select %s,%s,%s,%s,'owner'::member_role,true,'active'::membership_status,'en' "
            "from tenant where id=%s and slug=%s "
            "on conflict (id) do nothing",
            (member_id, TENANT_ID, AUTH_USER_ID, OWNER_EMAIL, TENANT_ID, SLUG),
        )
        owner = conn.execute(
            "select id from membership where tenant_id=%s and id=%s and user_id=%s "
            "and email=%s and role='owner' and status='active' and is_active_workspace",
            (TENANT_ID, member_id, AUTH_USER_ID, OWNER_EMAIL),
        ).fetchone()
        if owner is None:
            raise FixtureRefused("The reserved gallery membership is inconsistent")
        with conn.cursor() as cursor:
            assign_default_plan_in_signup(cursor, tenant_id=TENANT_ID)
        if tenant is None:
            conn.execute(
                "select record_audit_event('tenant.created','success',%s,%s,%s,%s::jsonb)",
                (
                    TENANT_ID,
                    member_id,
                    OWNER_EMAIL,
                    json.dumps({"slug": SLUG, "fixture": SLUG}),
                ),
            )
        documents = []
        for index, filename in enumerate(FILENAMES):
            document = ident(f"document-{index}")
            path = f"tenants/{TENANT_ID}/quotations/{document}/{filename}"
            digest = hashlib.sha256(source_pdf(index)).hexdigest()
            conn.execute(
                "insert into document (id,tenant_id,storage_bucket,storage_path,mime_type,content_hash,"
                "source_channel,status,created_by,created_at,original_filename) "
                "select %s,%s,'quotation-documents',%s,'application/pdf',%s,"
                "'upload'::document_source_channel,'uploaded'::document_status,%s,%s,%s "
                "from tenant where id=%s and slug=%s on conflict (id) do nothing",
                (
                    document,
                    TENANT_ID,
                    path,
                    digest,
                    member_id,
                    AT,
                    filename,
                    TENANT_ID,
                    SLUG,
                ),
            )
            existing = conn.execute(
                "select id from document where tenant_id=%s and id=%s and storage_path=%s and content_hash=%s",
                (TENANT_ID, document, path, digest),
            ).fetchone()
            if existing is None:
                raise FixtureRefused(
                    "An existing gallery source document differs from the deterministic fixture"
                )
            documents.append(
                {
                    "document_id": str(document),
                    "upload_url": f"{env['SUPABASE_URL']}/storage/v1/object/quotation-documents/{path}",
                }
            )
        return {
            "tenantId": str(TENANT_ID),
            "slug": SLUG,
            "ownerEmail": OWNER_EMAIL,
            "businessName": TENANT_NAME,
            "supabaseUrl": env["SUPABASE_URL"],
            "documents": documents,
        }


def money(amount: Decimal | int | str) -> dict[str, str]:
    return {"amount": format(Decimal(amount), ".4f"), "currency": "EGP"}


def source_pdf(index: int) -> bytes:
    """A real catalog/pages/content/xref PDF, with embedded Arabic font and fixed metadata."""
    font = (
        ROOT / "apps/api/src/procurepilot_api/assets/fonts/NotoNaskhArabic-Regular.ttf"
    )
    pdfmetrics.registerFont(TTFont("GalleryArabic", str(font)))
    output = io.BytesIO()
    canvas = Canvas(output, pagesize=(540, 640), invariant=1, pageCompression=0)
    canvas.setTitle("Food-service quotation - synthetic demonstration data")
    canvas.setAuthor("ProcurePilot demonstration fixtures")
    canvas.setFillColorRGB(0.12, 0.18, 0.24)

    def text(y: int, en: str, ar: str, size: int = 13) -> None:
        canvas.setFont("Helvetica", size)
        canvas.drawString(32, y, en)
        canvas.setFont("GalleryArabic", size)
        canvas.drawRightString(508, y - 23, get_display(arabic_reshaper.reshape(ar)))

    latin, arabic = SUPPLIERS[index].split(" | ")
    text(600, latin, arabic, 19)
    text(535, "Food-service quotation - 15 Oct 2026", "عرض أسعار مستلزمات المطاعم", 14)
    text(480, "Fennel Courtyard Kitchens - Cairo", "مطابخ فناء الشمر - القاهرة")
    canvas.line(32, 430, 508, 430)
    for p, (size, price) in enumerate(PACKS[index]):
        en, ar = PRODUCTS[p].split(" | ")
        text(400 - p * 90, en, ar, 15)
        canvas.setFont("Helvetica", 13)
        canvas.drawString(
            32, 355 - p * 90, f"2 packs x {size} kg    EGP {price:,.2f} / pack"
        )
    text(
        205,
        f"Delivery: 2 lines x EGP {DELIVERY[index]:.2f} = EGP {2 * DELIVERY[index]:.2f}",
        "رسوم التوصيل المسجلة للصنفين",
    )
    total = sum(2 * price + DELIVERY[index] for _, price in PACKS[index])
    text(145, f"Total: EGP {total:,.2f}", "الإجمالي بالجنيه المصري", 17)
    canvas.line(32, 95, 508, 95)
    text(
        72,
        "Synthetic demonstration data - not a supplier document",
        "بيانات اصطناعية للعرض - ليست وثيقة مورد",
        11,
    )
    canvas.showPage()
    canvas.save()
    return output.getvalue()


def seed(payload: dict[str, object]) -> dict[str, object]:
    env = hosted_environment()
    if (
        payload.get("tenantId") != str(TENANT_ID)
        or payload.get("ownerEmail") != OWNER_EMAIL
    ):
        raise FixtureRefused(
            "Seed payload does not identify the reserved gallery owner and tenant"
        )
    documents = [str(ident(f"document-{index}")) for index in range(3)]
    with db.connect(
        env["DATABASE_URL"], row_factory=dict_row, sslmode="require", connect_timeout=20
    ) as conn:
        conn.execute("reset role")
        conn.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (SLUG,))
        owned_tenant(conn)
        owner = conn.execute(
            "select id, tenant_id from membership where tenant_id=%s and id=%s and user_id=%s "
            "and email=%s and role='owner' and status='active' and is_active_workspace",
            (TENANT_ID, ident("owner-membership"), AUTH_USER_ID, OWNER_EMAIL),
        ).fetchone()
        if owner is None:
            raise FixtureRefused(
                "Gallery owner has no active membership in its reserved tenant"
            )
        tenant_id, member_id = TENANT_ID, owner["id"]

        def insert(table: str, key: str, **values: object) -> UUID:
            row = {"id": ident(key), "tenant_id": tenant_id, **values}
            parameters = list(row.values())
            source = sql.SQL("values ({})")
            if table == "canonical_product":
                del row["tenant_id"]
                # The schema's global spine has no tenant_id column. Authorise these two
                # reserved rows via the owning tenant and give them tenant-derived IDs/brand.
                source = sql.SQL(
                    "select {} where exists (select 1 from tenant where id=%s and slug=%s)"
                )
                parameters = [*row.values(), tenant_id, SLUG]
            # Each tenant-scoped INSERT supplies tenant_id explicitly. IDs derive from that
            # reserved tenant, and conflicts are checked inside the same ownership scope.
            conn.execute(
                sql.SQL("insert into {} ({}) {} on conflict (id) do nothing").format(
                    sql.Identifier(table),
                    sql.SQL(", ").join(map(sql.Identifier, row)),
                    source.format(sql.SQL(", ").join(sql.Placeholder() for _ in row)),
                ),
                parameters,
            )
            scope = sql.SQL("id=%s and tenant_id=%s")
            scope_values = [ident(key), tenant_id]
            if table == "canonical_product":
                # Canonical products are global in this schema. Only our two deterministic,
                # explicitly branded fixture records may be created/reused; never search names.
                scope = sql.SQL("id=%s and brand=%s")
                scope_values = [ident(key), SLUG]
            existing = conn.execute(
                sql.SQL("select * from {} where {}").format(
                    sql.Identifier(table), scope
                ),
                scope_values,
            ).fetchone()
            if existing is None:
                raise FixtureRefused(
                    "A fixture ID is not owned by the reserved gallery tenant"
                )
            for column, expected in row.items():
                stored = existing[column]
                if isinstance(expected, Jsonb):
                    expected = expected.obj
                if isinstance(stored, Decimal):
                    expected = Decimal(str(expected))
                if isinstance(stored, date) and isinstance(expected, str):
                    expected = date.fromisoformat(expected)
                if stored != expected:
                    raise FixtureRefused(
                        "Existing gallery fixture data differs; refusing an implicit rewrite"
                    )
            return ident(key)

        product_ids = []
        for p, name in enumerate(PRODUCTS):
            canonical = insert(
                "canonical_product",
                f"canonical-{p}",
                name=name,
                brand=SLUG,
                base_unit="kilogram",
                created_at=AT,
            )
            product = insert(
                "workspace_product",
                f"product-{p}",
                canonical_product_id=canonical,
                tenant_name=name,
                created_at=AT,
            )
            insert(
                "pack_definition",
                f"pack-{p}",
                workspace_product_id=product,
                pack_count=1,
                unit_size=25 if p == 0 else 10,
                created_at=AT,
            )
            product_ids.append(product)

        # Branches and budgets use fixed commercial dates, not wall-clock-dependent periods.
        branches = []
        for b, name in enumerate(
            ["Maadi kitchen | مطبخ المعادي", "Heliopolis kitchen | مطبخ مصر الجديدة"]
        ):
            branch = insert(
                "branch",
                f"branch-{b}",
                name=name,
                region="EG",
                address="Cairo | القاهرة",
                created_at=AT,
                updated_at=AT,
            )
            insert(
                "budget",
                f"budget-{b}",
                amount=20000,
                currency="EGP",
                period="monthly",
                period_start="2026-10-01",
                scope="branch",
                branch_id=branch,
                created_by=member_id,
                created_at=AT,
                updated_at=AT,
            )
            branches.append(branch)
        centre = insert(
            "cost_centre",
            "centre",
            name="Kitchen staples | أساسيات المطبخ",
            code="KITCHEN",
            branch_id=branches[0],
            budget_owner_membership_id=member_id,
            created_at=AT,
            updated_at=AT,
        )

        supplier_ids = []
        for s, name in enumerate(SUPPLIERS):
            supplier = insert(
                "supplier",
                f"supplier-{s}",
                name=name,
                lead_time_days=s + 1,
                delivery_fee_amount=DELIVERY[s],
                delivery_fee_currency="EGP",
                created_at=AT,
            )
            supplier_ids.append(supplier)
            insert(
                "supplier_commercial_term",
                f"terms-{s}",
                supplier_id=supplier,
                effective_from=AT,
                delivery_fee_amount=DELIVERY[s],
                delivery_fee_currency="EGP",
                created_by_membership_id=member_id,
                created_at=AT,
            )
            document_id = UUID(str(documents[s]))
            # Deterministic metadata was created by bootstrap; bytes used the real JWT upload.
            document = conn.execute(
                "select id from document where id=%s and tenant_id=%s and created_by=%s",
                (document_id, tenant_id, member_id),
            ).fetchone()
            if document is None:
                raise FixtureRefused(
                    "Gallery source document is missing from its reserved tenant"
                )
            total = sum(2 * price + DELIVERY[s] for _, price in PACKS[s])
            quotation = insert(
                "quotation",
                f"quotation-{s}",
                document_id=document_id,
                supplier_id=supplier,
                currency="EGP",
                issue_date="2026-10-15",
                status="reviewed",
                arithmetic_status="reconciled",
                stated_total_amount=total,
                stated_total_currency="EGP",
                reviewed_by=member_id,
                reviewed_at=AT,
                created_at=AT,
            )
            for field, value in {
                "supplier_name": name,
                "currency": "EGP",
                "issue_date": "2026-10-15",
                "stated_total": money(total),
            }.items():
                insert(
                    "field_extraction",
                    f"field-{s}-{field}",
                    quotation_id=quotation,
                    entity_type="quotation",
                    entity_id=quotation,
                    field_name=field,
                    extracted_value=Jsonb(value),
                    confidence="0.98",
                    source_page=1,
                    extraction_method="structured_parse",
                    model_version="gallery-source-v1",
                    created_at=AT,
                )
            for p, (pack_size, price) in enumerate(PACKS[s]):
                line = insert(
                    "quotation_line",
                    f"line-{s}-{p}",
                    quotation_id=quotation,
                    line_number=p + 1,
                    original_text=PRODUCTS[p],
                    quantity=2,
                    pack_count=1,
                    unit_size=pack_size,
                    pack_unit="kilogram",
                    unit_price_amount=price,
                    unit_price_currency="EGP",
                    vat_rate=0,
                    delivery_fee_amount=DELIVERY[s],
                    delivery_fee_currency="EGP",
                    discount_amount=0,
                    discount_currency="EGP",
                    created_at=AT,
                )
                for field, value in {
                    "original_text": PRODUCTS[p],
                    "quantity": "2",
                    "unit_price": money(price),
                    "pack": {
                        "pack_count": 1,
                        "unit_size": str(pack_size),
                        "unit": "kilogram",
                    },
                }.items():
                    insert(
                        "field_extraction",
                        f"field-{s}-{p}-{field}",
                        quotation_id=quotation,
                        entity_type="quotation_line",
                        entity_id=line,
                        field_name=field,
                        extracted_value=Jsonb(value),
                        confidence="0.98",
                        source_page=1,
                        extraction_method="structured_parse",
                        model_version="gallery-source-v1",
                        created_at=AT,
                    )
                decision = insert(
                    "match_decision",
                    f"decision-{s}-{p}",
                    quotation_line_id=line,
                    matched_workspace_product_id=product_ids[p],
                    outcome="no_match_new_product",
                    is_automatic=False,
                    decided_by=member_id,
                    decided_at=AT,
                    confidence="0.98",
                    created_at=AT,
                )
                # The offers API projects from the catalogue purchasing pack (ADR-020).
                # Persist the explicit conversion at the normalisation boundary, retaining
                # source pack/price in both quotation_line and the replay evidence. For example,
                # 2 x 10kg at EGP440 becomes 0.8 x 25kg at EGP1100, with the same EGP880 goods.
                catalogue_size = Decimal([25, 10][p])
                result = compute_landed_cost(
                    LandedCostInputs(
                        quantity=Decimal(2 * pack_size) / catalogue_size,
                        normalised_base_quantity=Decimal(2 * pack_size),
                        base_unit="kilogram",
                        unit_price=MoneyValue(
                            Decimal(price) * catalogue_size / pack_size, "EGP"
                        ),
                        vat_rate=Decimal(0),
                        delivery_fee=MoneyValue(Decimal(DELIVERY[s]), "EGP"),
                        discount=MoneyValue(Decimal(0), "EGP"),
                    )
                )
                result.raw_inputs["source_pack_conversion"] = {
                    "source_quantity": "2",
                    "source_pack_kg": str(pack_size),
                    "source_pack_price": money(price),
                    "catalogue_pack_kg": str(catalogue_size),
                    "rule_version": "gallery-pack-conversion-v1",
                    "quotation_line_id": str(line),
                }
                values: dict[str, object] = {}
                for column, value in [
                    ("unit_price", result.unit_price),
                    ("vat", result.vat_amount),
                    ("delivery_fee", result.delivery_fee),
                    ("discount", result.discount),
                    ("other_charges", result.other_charges),
                    ("total", result.total),
                ]:
                    values[f"{column}_amount"] = value.amount
                    values[f"{column}_currency"] = value.currency
                insert(
                    "landed_cost",
                    f"cost-{s}-{p}",
                    quotation_line_id=line,
                    match_decision_id=decision,
                    quantity=result.quantity,
                    normalised_base_quantity=result.normalised_base_quantity,
                    base_unit="kilogram",
                    raw_inputs=Jsonb(result.raw_inputs),
                    rule_version=result.rule_version,
                    valid_from=AT,
                    recorded_at=AT + timedelta(minutes=s),
                    created_at=AT,
                    **values,
                )

        # A completed two-supplier allocation. Each item is assigned whole to its cheaper offer.
        # Request 50kg rice + 20kg lentils: 2040 + 1250 = 3290 EGP; baselines 3480 / 3500.
        # Source delivery is PER LINE (as in the PDF and raw inputs), so no fee is counted twice.
        quantities = [Decimal(50), Decimal(20)]
        projected = [
            [
                (Decimal(PACKS[s][p][1]) * quantities[p] / PACKS[s][p][0] + DELIVERY[s])
                for p in range(2)
            ]
            for s in range(2)
        ]
        assert projected == [
            [Decimal(2040), Decimal(1440)],
            [Decimal(2250), Decimal(1250)],
        ]
        allocation = []
        for s, p in [(0, 0), (1, 1)]:
            allocation.append(
                {
                    "supplier_id": str(supplier_ids[s]),
                    "lines": [
                        {
                            "supplier_id": str(supplier_ids[s]),
                            "workspace_product_id": str(product_ids[p]),
                            "quantity": str(quantities[p]),
                            "offer_id": str(ident(f"cost-{s}-{p}")),
                            "landed_cost": money(projected[s][p]),
                        }
                    ],
                    "total_landed_cost": money(projected[s][p]),
                }
            )
        items = [
            {
                "workspace_product_id": str(product_ids[p]),
                "quantity": str(quantities[p]),
            }
            for p in range(2)
        ]
        result = {
            "feasible": True,
            "allocation": allocation,
            "total_landed_cost": money(3290),
            "single_supplier_baselines": [
                {
                    "supplier_id": str(supplier_ids[s]),
                    "feasible": True,
                    "total_landed_cost": money(sum(projected[s])),
                }
                for s in range(2)
            ],
            "infeasible_items": [],
            "applied_constraints": [
                {
                    "kind": "delivery_fee",
                    "supplier_id": str(supplier_ids[s]),
                    "description": "Recorded delivery per allocated line",
                    "money": money(DELIVERY[s]),
                    "source_ids": [str(ident(f"terms-{s}"))],
                }
                for s in range(2)
            ],
            "violated_constraints": [],
            "risk_notes": [],
            "confidence": "medium",
            "source_landed_cost_ids": [str(ident("cost-0-0")), str(ident("cost-1-1"))],
            "solver_version": "gallery-enumeration-v1",
            "computed_at": AT.isoformat(),
        }
        snapshot = {
            "kind": "advanced_basket_optimisation",
            "rule_version": "gallery-enumeration-v1",
            "items": items,
            "pack_snapshot": {
                str(product_ids[p]): {
                    "base_quantity": str([25, 10][p]),
                    "base_unit": "kilogram",
                }
                for p in range(2)
            },
            "source_landed_cost_ids": [
                str(ident(f"cost-{s}-{p}")) for s in range(2) for p in range(2)
            ],
            "supplier_terms": [
                {
                    "supplier_id": str(supplier_ids[s]),
                    "delivery_fee": money(DELIVERY[s]),
                    "application": "per_line",
                }
                for s in range(2)
            ],
        }
        basket = insert(
            "basket_split_job",
            "basket",
            requested_by=member_id,
            supplier_ids=supplier_ids[:2],
            items=Jsonb(items),
            request_snapshot=Jsonb(snapshot),
            status="completed",
            result=Jsonb(result),
            created_at=AT,
            started_at=AT,
            completed_at=AT,
        )
        # Exercise the exact API deserialiser, including its legacy/advanced union, before capture.
        job = conn.execute(
            "select * from basket_split_job where id=%s and tenant_id=%s",
            (basket, tenant_id),
        ).fetchone()
        assert job and _job(job).result.feasible

        request = insert(
            "purchase_request",
            "request",
            branch_id=branches[0],
            cost_centre_id=centre,
            requested_by_membership_id=member_id,
            required_by_date="2026-10-22",
            status="submitted",
            estimated_total_amount=3290,
            estimated_total_currency="EGP",
            has_incomplete_estimate=False,
            submitted_at=AT,
            created_at=AT,
            updated_at=AT,
        )
        for p, s in [(0, 0), (1, 1)]:
            insert(
                "purchase_request_line",
                f"request-line-{p}",
                purchase_request_id=request,
                workspace_product_id=product_ids[p],
                quantity=quantities[p],
                estimated_unit_price_amount=projected[s][p] / quantities[p],
                estimated_unit_price_currency="EGP",
                estimated_unit_price_source_landed_cost_id=ident(f"cost-{s}-{p}"),
                estimated_at=AT,
                created_at=AT,
            )
        insert(
            "approval_step",
            "approval",
            purchase_request_id=request,
            assigned_membership_id=member_id,
            source="owner_fallback",
            created_at=AT,
        )

        for p in range(2):
            # Use the application's real baseline calculation, with linked quotation/match/cost
            # evidence, rather than inventing a flattering delta or a baseless verified badge.
            actual = Decimal([2040, 1250][p])
            # The application's baseline reader runs under RLS too, including its joins.
            conn.execute("set local role authenticated")
            conn.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (
                    json.dumps(
                        {
                            "sub": str(AUTH_USER_ID),
                            "tenant_id": str(tenant_id),
                            "role": "authenticated",
                            "member_role": "owner",
                        }
                    ),
                ),
            )
            baseline = capture_baseline(
                conn,
                product_id=product_ids[p],
                quantity=quantities[p],
                actual=Money(amount=actual, currency="EGP"),
                base_unit="kilogram",
            )
            conn.execute("reset role")
            assert baseline.value and baseline.delta and baseline.delta.amount > 0
            supplier_index = p
            purchase = insert(
                "purchase_record",
                f"purchase-{p}",
                workspace_product_id=product_ids[p],
                supplier_id=supplier_ids[supplier_index],
                quotation_line_id=ident(f"line-{supplier_index}-{p}"),
                match_decision_id=ident(f"decision-{supplier_index}-{p}"),
                landed_cost_id=ident(f"cost-{supplier_index}-{p}"),
                recorded_by=member_id,
                quantity=quantities[p],
                base_unit="kilogram",
                unit_price_amount=actual / quantities[p],
                unit_price_currency="EGP",
                total_paid_amount=actual,
                total_paid_currency="EGP",
                delivery_result="delivered",
                ordered_at=AT + timedelta(minutes=3),
                delivered_at=AT + timedelta(minutes=5),
                recorded_at=AT + timedelta(minutes=10),
                created_at=AT + timedelta(minutes=10),
                updated_at=AT + timedelta(minutes=10),
                notes="Synthetic demonstration purchase | عملية شراء اصطناعية للعرض",
            )
            insert(
                "saving_record",
                f"saving-{p}",
                purchase_record_id=purchase,
                workspace_product_id=product_ids[p],
                supplier_id=supplier_ids[supplier_index],
                status="verified" if p == 0 else "pending",
                baseline_policy=baseline.policy,
                baseline_source_landed_cost_ids=baseline.source_landed_cost_ids,
                baseline_unit_price_amount=baseline.unit_price.amount,
                baseline_unit_price_currency="EGP",
                baseline_value_amount=baseline.value.amount,
                baseline_value_currency="EGP",
                actual_value_amount=actual,
                actual_value_currency="EGP",
                delta_amount=baseline.delta.amount,
                delta_currency="EGP",
                calculation_version=CALCULATION_VERSION,
                calculation_inputs=Jsonb(baseline.calculation_inputs),
                recorded_by=member_id,
                recorded_at=AT + timedelta(minutes=10),
                verified_by=member_id if p == 0 else None,
                verified_at=AT + timedelta(minutes=20) if p == 0 else None,
                created_at=AT + timedelta(minutes=10),
            )

        return {
            "quotationId": str(ident("quotation-0")),
            "productId": str(product_ids[0]),
            "basketId": str(basket),
            "savingId": str(ident("saving-0")),
            "verifiedDelta": str(
                conn.execute(
                    "select delta_amount from saving_record where id=%s and tenant_id=%s",
                    (ident("saving-0"), tenant_id),
                ).fetchone()["delta_amount"]
            ),
        }


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--pdf":
            print(base64.b64encode(source_pdf(int(sys.argv[2]))).decode())
        elif sys.argv[1:] == ["--check"]:
            hosted_environment()  # Offline, no connection and no secret output.
            print(
                json.dumps(
                    {"poolerHost": POOLER_HOST, "sessionPort": 5432, "slug": SLUG}
                )
            )
        elif sys.argv[1:] == ["--bootstrap"]:
            print(json.dumps(bootstrap(json.load(sys.stdin))))
        elif not sys.argv[1:]:
            print(json.dumps(seed(json.load(sys.stdin))))
        else:
            raise FixtureRefused("Unknown gallery fixture command")
    except FixtureRefused as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:  # noqa: BLE001 -- CLI boundary must redact all credential-bearing failures.
        # Driver/Auth exceptions can contain DSNs, request bodies or credentials. Never emit
        # their text/traceback. The orchestrator can diagnose using the scoped hosted logs.
        print(
            "Hosted gallery fixture operation failed; credentials and driver details omitted",
            file=sys.stderr,
        )
        sys.exit(1)
