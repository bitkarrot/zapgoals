from datetime import datetime, timezone
from typing import Any

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import Contribution, ExtensionSetting, Goal, GoalData

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


async def has_paid_contributions(goal_id: str) -> bool:
    row: Any = await db.fetchone(
        "SELECT payment_hash FROM zapgoals.contributions "
        "WHERE goal_id = :goal_id AND paid = true LIMIT 1",
        {"goal_id": goal_id},
    )
    return bool(row)


async def delete_goal_and_unpaid_contributions(goal_id: str) -> None:
    async with db.connect() as conn:
        await conn.execute(
            "DELETE FROM zapgoals.contributions "
            "WHERE goal_id = :goal_id AND paid = false",
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
