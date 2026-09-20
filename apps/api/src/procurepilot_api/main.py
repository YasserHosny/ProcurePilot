from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import register_exception_handlers
from procurepilot_api.modules.accounting.router import router as accounting_router
from procurepilot_api.modules.alerts.router import router as alerts_router
from procurepilot_api.modules.auth.router import router as auth_router
from procurepilot_api.modules.billing.router import router as billing_router
from procurepilot_api.modules.catalogue.router import router as catalogue_router
from procurepilot_api.modules.devices.router import router as devices_router
from procurepilot_api.modules.digests.router import router as digests_router
from procurepilot_api.modules.documents.router import router as documents_router
from procurepilot_api.modules.exports.router import router as exports_router
from procurepilot_api.modules.extraction.router import router as extraction_router
from procurepilot_api.modules.forecasting.router import router as forecasting_router
from procurepilot_api.modules.health.router import router as health_router
from procurepilot_api.modules.ingestion.router import router as ingestion_router
from procurepilot_api.modules.jobs.router import router as jobs_router
from procurepilot_api.modules.landed_cost.router import router as landed_cost_router
from procurepilot_api.modules.matching.router import router as matching_router
from procurepilot_api.modules.members.router import router as members_router
from procurepilot_api.modules.offers.router import router as offers_router
from procurepilot_api.modules.orders.router import router as orders_router
from procurepilot_api.modules.organisation.router import router as organisation_router
from procurepilot_api.modules.partner.router import router as partner_router
from procurepilot_api.modules.pos.router import router as pos_router
from procurepilot_api.modules.quotations.router import router as quotations_router
from procurepilot_api.modules.reports.router import router as reports_router
from procurepilot_api.modules.requests.router import router as requests_router
from procurepilot_api.modules.savings.router import router as savings_router
from procurepilot_api.modules.tenants.router import router as tenants_router
from procurepilot_api.modules.webhooks.router import router as webhooks_router
from procurepilot_api.shared.logging import TraceIdMiddleware, configure_logging
from procurepilot_api.shared.observability import init_error_reporting
from procurepilot_api.shared.rate_limit import configure_rate_limiting

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    # Before anything else can fail, so that startup errors are reported too.
    init_error_reporting(active_settings)
    configure_logging(active_settings.api_log_level)

    app = FastAPI(title="ProcurePilot API")
    app.add_middleware(TraceIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.api_cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    configure_rate_limiting(app, active_settings)

    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(accounting_router, prefix=API_PREFIX)
    app.include_router(tenants_router, prefix=API_PREFIX)
    app.include_router(members_router, prefix=API_PREFIX)
    app.include_router(catalogue_router, prefix=API_PREFIX)
    app.include_router(devices_router, prefix=API_PREFIX)
    app.include_router(documents_router, prefix=API_PREFIX)
    app.include_router(quotations_router, prefix=API_PREFIX)
    app.include_router(extraction_router, prefix=API_PREFIX)
    app.include_router(forecasting_router, prefix=API_PREFIX)
    app.include_router(jobs_router, prefix=API_PREFIX)
    app.include_router(matching_router, prefix=API_PREFIX)
    app.include_router(landed_cost_router, prefix=API_PREFIX)
    app.include_router(offers_router, prefix=API_PREFIX)
    app.include_router(organisation_router, prefix=API_PREFIX)
    app.include_router(orders_router, prefix=API_PREFIX)
    app.include_router(requests_router, prefix=API_PREFIX)
    app.include_router(alerts_router, prefix=API_PREFIX)
    app.include_router(savings_router, prefix=API_PREFIX)
    app.include_router(exports_router, prefix=API_PREFIX)
    app.include_router(reports_router, prefix=API_PREFIX)
    app.include_router(digests_router, prefix=API_PREFIX)
    app.include_router(billing_router, prefix=API_PREFIX)
    app.include_router(ingestion_router, prefix=API_PREFIX)
    app.include_router(pos_router, prefix=API_PREFIX)
    app.include_router(partner_router, prefix=API_PREFIX)
    app.include_router(webhooks_router, prefix=API_PREFIX)
    return app


app = create_app()
