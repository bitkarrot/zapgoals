import asyncio

from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .services import process_settled_payment


async def wait_for_paid_invoices() -> None:
    invoice_queue: asyncio.Queue[Payment] = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_zapgoals")
    while True:
        payment = await invoice_queue.get()
        try:
            await on_invoice_paid(payment)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Could not process zapgoals invoice: {}", str(exc))


async def on_invoice_paid(payment: Payment) -> None:
    if not payment.extra or payment.extra.get("tag") != "zapgoals":
        return
    await process_settled_payment(payment)
