import asyncio

from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import clear_stale_sweeping_flags
from .services import SweepError, process_settled_payment, sweep_recurring_goal
from .settings import builtin_scheduler_interval_seconds


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


async def sweep_due_loop() -> None:
    """Periodically sweep all due recurring goals across all wallets.

    This is an optional built-in fallback for when the LNbits scheduler
    extension is not installed. It is gated by the ZAPGOALS_BUILTIN_SCHEDULER
    env flag. The preferred path is to use the scheduler extension to fire
    POST /zapgoals/api/v1/recurring/sweep-due on a cron schedule.
    """
    from lnbits.settings import settings

    await asyncio.sleep(10)
    while settings.lnbits_running:
        try:
            await clear_stale_sweeping_flags(300)
            due = await get_due_recurring_goals_all_wallets()
            for goal in due:
                try:
                    await sweep_recurring_goal(goal.id)
                except SweepError as exc:
                    logger.warning(
                        "Scheduled sweep failed for goal {}: {}",
                        goal.id,
                        str(exc),
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("zapgoals sweep loop error: {}", str(exc))
        await asyncio.sleep(builtin_scheduler_interval_seconds)


async def get_due_recurring_goals_all_wallets():
    """Fetch due recurring goals across all wallets (not scoped to one)."""
    from datetime import datetime, timezone

    from .crud import db
    from .models import Goal

    now = datetime.now(timezone.utc)
    return await db.fetchall(
        "SELECT * FROM zapgoals.goals "
        "WHERE recurring = true AND sweeping = false "
        f"AND target_date <= {db.timestamp_placeholder('now')}",
        {"now": now},
        Goal,
    )
