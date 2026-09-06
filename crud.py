from datetime import datetime, timedelta, timezone

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import Contribution, ExtensionSetting, Goal, GoalData, Period

db = Database("ext_zapgoals")


async def create_goal(wallet_id: str, data: GoalData) -> Goal:
    now = datetime.now(timezone.utc)
    goal = Goal(
        id=urlsafe_short_hash(),
        wallet=wallet_id,
        current_amount=0,
        created_at=now,
        updated_at=now,
        **data.dict(),
    )
    await db.insert("zapgoals.goals", goal)
    return goal


async def get_goal(goal_id: str) -> Goal | None:
    return await db.fetchone(
        "SELECT * FROM zapgoals.goals WHERE id = :id", {"id": goal_id}, Goal
    )


async def get_goal_by_username(username: str) -> Goal | None:
    return await db.fetchone(
        "SELECT * FROM zapgoals.goals " "WHERE lightning_address_username = :username",
        {"username": username},
        Goal,
    )


async def get_goals(wallet_id: str) -> list[Goal]:
    return await db.fetchall(
        "SELECT * FROM zapgoals.goals WHERE wallet = :wallet "
        "ORDER BY created_at DESC",
        {"wallet": wallet_id},
        Goal,
    )


async def update_goal(existing: Goal, data: GoalData) -> Goal:
    values = data.dict()
    values.update(
        {
            "id": existing.id,
            "wallet": existing.wallet,
            "current_amount": existing.current_amount,
            "created_at": existing.created_at,
            "updated_at": datetime.now(timezone.utc),
            "period_index": existing.period_index,
            "period_start": existing.period_start,
            "last_swept_at": existing.last_swept_at,
            "sweeping": existing.sweeping,
        }
    )
    goal = Goal(**values)
    await db.update("zapgoals.goals", goal)
    return goal


async def create_contribution(
    payment_hash: str, goal_id: str, amount: int, source: str
) -> Contribution:
    contribution = Contribution(
        payment_hash=payment_hash,
        goal_id=goal_id,
        amount=amount,
        source=source,
        created_at=datetime.now(timezone.utc),
    )
    await db.insert("zapgoals.contributions", contribution)
    return contribution


async def get_contribution(payment_hash: str) -> Contribution | None:
    return await db.fetchone(
        "SELECT * FROM zapgoals.contributions WHERE payment_hash = :payment_hash",
        {"payment_hash": payment_hash},
        Contribution,
    )


async def purge_expired_unpaid_contributions(goal_id: str, expiry_seconds: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=expiry_seconds)
    await db.execute(
        "DELETE FROM zapgoals.contributions WHERE goal_id = :goal_id "
        "AND paid = false AND created_at < "
        f"{db.timestamp_placeholder('cutoff')}",
        {"goal_id": goal_id, "cutoff": cutoff},
    )


async def delete_goal_and_contributions(goal_id: str) -> None:
    async with db.connect() as conn:
        await conn.execute(
            "DELETE FROM zapgoals.contributions WHERE goal_id = :goal_id",
            {"goal_id": goal_id},
        )
        await conn.execute(
            "DELETE FROM zapgoals.goals WHERE id = :goal_id", {"goal_id": goal_id}
        )


async def settle_contribution(payment_hash: str) -> Goal | None:
    now = datetime.now(timezone.utc)
    async with db.connect() as conn:
        contribution = await conn.fetchone(
            "SELECT * FROM zapgoals.contributions "
            "WHERE payment_hash = :payment_hash",
            {"payment_hash": payment_hash},
            Contribution,
        )
        if not contribution:
            return None
        result = await conn.execute(
            "UPDATE zapgoals.contributions SET paid = true, paid_at = :paid_at "
            "WHERE payment_hash = :payment_hash AND paid = false",
            {"payment_hash": payment_hash, "paid_at": now},
        )
        if result.rowcount != 1:
            return None
        await conn.execute(
            "UPDATE zapgoals.goals SET current_amount = current_amount + :amount, "
            "updated_at = :updated_at WHERE id = :goal_id",
            {
                "amount": contribution.amount,
                "updated_at": now,
                "goal_id": contribution.goal_id,
            },
        )
        return await conn.fetchone(
            "SELECT * FROM zapgoals.goals WHERE id = :goal_id",
            {"goal_id": contribution.goal_id},
            Goal,
        )


async def get_extension_setting() -> ExtensionSetting | None:
    return await db.fetchone(
        "SELECT * FROM zapgoals.settings WHERE id = 'singleton'",
        model=ExtensionSetting,
    )


async def create_extension_setting(private_key: str) -> ExtensionSetting:
    setting = ExtensionSetting(nostr_private_key=private_key)
    await db.insert("zapgoals.settings", setting)
    return setting


async def create_period(period: Period) -> Period:
    await db.insert("zapgoals.periods", period)
    return period


async def get_periods(goal_id: str) -> list[Period]:
    return await db.fetchall(
        "SELECT * FROM zapgoals.periods WHERE goal_id = :goal_id "
        "ORDER BY period_index ASC",
        {"goal_id": goal_id},
        Period,
    )


async def get_due_recurring_goals(wallet_id: str) -> list[Goal]:
    now = datetime.now(timezone.utc)
    return await db.fetchall(
        "SELECT * FROM zapgoals.goals "
        "WHERE wallet = :wallet AND recurring = true AND sweeping = false "
        f"AND target_date <= {db.timestamp_placeholder('now')}",
        {"wallet": wallet_id, "now": now},
        Goal,
    )


async def clear_stale_sweeping_flags(timeout_seconds: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    result = await db.execute(
        "UPDATE zapgoals.goals SET sweeping = false "
        "WHERE sweeping = true "
        f"AND updated_at < {db.timestamp_placeholder('cutoff')}",
        {"cutoff": cutoff},
    )
    return result.rowcount if hasattr(result, "rowcount") else 0


async def acquire_sweep_lock(goal_id: str) -> bool:
    """Atomically set sweeping=true. Returns True if the lock was acquired."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        "UPDATE zapgoals.goals SET sweeping = true, updated_at = :updated_at "
        "WHERE id = :goal_id AND sweeping = false",
        {"goal_id": goal_id, "updated_at": now},
    )
    return result.rowcount == 1


async def release_sweep_lock(goal_id: str) -> None:
    await db.execute(
        "UPDATE zapgoals.goals SET sweeping = false WHERE id = :goal_id",
        {"goal_id": goal_id},
    )


async def complete_sweep(
    goal_id: str,
    new_current: int,
    new_period_index: int,
    new_period_start: datetime,
    new_target_date: datetime,
    period: Period,
) -> Goal | None:
    """Atomically record the period ledger row and advance the goal."""
    now = datetime.now(timezone.utc)
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO zapgoals.periods "
            "(id, goal_id, period_index, period_start, period_end, "
            "zapped_total, moved_to_target, rollover, sweep_mode, swept_at) "
            "VALUES (:id, :goal_id, :period_index, :period_start, :period_end, "
            ":zapped_total, :moved_to_target, :rollover, :sweep_mode, :swept_at)",
            {
                "id": period.id,
                "goal_id": period.goal_id,
                "period_index": period.period_index,
                "period_start": period.period_start,
                "period_end": period.period_end,
                "zapped_total": period.zapped_total,
                "moved_to_target": period.moved_to_target,
                "rollover": period.rollover,
                "sweep_mode": period.sweep_mode,
                "swept_at": period.swept_at,
            },
        )
        await conn.execute(
            "UPDATE zapgoals.goals SET current_amount = :current_amount, "
            "period_index = :period_index, period_start = :period_start, "
            "target_date = :target_date, last_swept_at = :last_swept_at, "
            "sweeping = false, updated_at = :updated_at "
            "WHERE id = :goal_id",
            {
                "current_amount": new_current,
                "period_index": new_period_index,
                "period_start": new_period_start,
                "target_date": new_target_date,
                "last_swept_at": now,
                "updated_at": now,
                "goal_id": goal_id,
            },
        )
        return await conn.fetchone(
            "SELECT * FROM zapgoals.goals WHERE id = :goal_id",
            {"goal_id": goal_id},
            Goal,
        )
