import asyncio

from fastapi import APIRouter
from loguru import logger

from .crud import db
from .settings import lightning_address_enabled
from .tasks import wait_for_paid_invoices
from .views import zapgoals_generic_router
from .views_api import zapgoals_api_router

zapgoals_ext = APIRouter(prefix="/zapgoals", tags=["Zap Goals"])
zapgoals_ext.include_router(zapgoals_generic_router)
zapgoals_ext.include_router(zapgoals_api_router)

zapgoals_static_files = [{"path": "/zapgoals/static", "name": "zapgoals_static"}]

zapgoals_redirect_paths = (
    [
        {
            "from_path": "/.well-known/lnurlp",
            "redirect_to_path": "/api/v1/well-known",
        }
    ]
    if lightning_address_enabled
    else []
)

scheduled_tasks: list[asyncio.Task] = []


def zapgoals_start() -> None:
    from lnbits.tasks import create_permanent_unique_task

    task = create_permanent_unique_task("ext_zapgoals", wait_for_paid_invoices)
    scheduled_tasks.append(task)


def zapgoals_stop() -> None:
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as exc:
            logger.warning("Could not stop zapgoals task: {}", str(exc))


__all__ = [
    "db",
    "zapgoals_ext",
    "zapgoals_redirect_paths",
    "zapgoals_start",
    "zapgoals_static_files",
    "zapgoals_stop",
]
