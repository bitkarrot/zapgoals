import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from lnbits import db as lnbits_db
from lnbits.core.models import WalletTypeInfo
from lnbits.settings import settings

from .. import crud, migrations, views_api, zapgoals_ext
from ..models import Goal, GoalData


def goal_data(**overrides):
    return GoalData(
        **{
            "title": "Recurring display test",
            "goal_amount": 1000,
            "target_date": datetime.now(timezone.utc) + timedelta(days=30),
            "recurring": True,
            "recurrence_unit": "month",
            "target_wallet_id": "test-target",
            **overrides,
        }
    )


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "lnbits_data_folder", str(tmp_path))
    monkeypatch.setattr(settings, "lnbits_database_url", None)
    monkeypatch.setattr(lnbits_db, "DB_TYPE", lnbits_db.SQLITE)
    db = lnbits_db.Database("ext_zapgoals")
    assert str(tmp_path) in db.path
    monkeypatch.setattr(crud, "db", db)
    return db


async def migrate_old_schema(db):
    for migrate in (
        migrations.m001_initial,
        migrations.m002_suggested_amounts_and_wallet_modes,
        migrations.m003_font_name_and_weight,
        migrations.m004_recurring,
    ):
        await migrate(db)


def test_badge_migration_preserves_existing_goals_and_defaults_visible(
    isolated_database,
):
    async def check():
        db = isolated_database
        try:
            await migrate_old_schema(db)
            now = datetime.now(timezone.utc)
            legacy = Goal(
                id="legacy-goal",
                wallet="test-wallet",
                created_at=now,
                updated_at=now,
                current_amount=117,
                period_index=2,
                period_start=now - timedelta(days=10),
                **goal_data().dict(),
            )
            # Insert exactly the pre-upgrade fields, before the new column exists.
            fields = legacy.dict(exclude={"show_period_badge"})
            async with db.connect() as conn:
                values = lnbits_db.model_to_dict(legacy)
                values.pop("show_period_badge")
                await conn.execute(
                    f"INSERT INTO zapgoals.goals ({', '.join(fields)}) "
                    f"VALUES ({', '.join(':' + field for field in fields)})",
                    values,
                )
            before = dict(await db.fetchone("SELECT * FROM zapgoals.goals"))
            await migrations.m005_public_period_badge(db)
            after = dict(await db.fetchone("SELECT * FROM zapgoals.goals"))
            assert after.pop("show_period_badge") == 1
            assert after == before
            loaded = await crud.get_goal(legacy.id)
            assert loaded is not None
            assert loaded.show_period_badge is True
            assert loaded.current_amount == 117
            assert loaded.period_index == 2
        finally:
            await db.engine.dispose()

    asyncio.run(check())


@pytest.mark.parametrize("visible", [True, False])
def test_saved_visibility_roundtrips_through_owner_and_public_api(
    isolated_database, visible
):
    async def check():
        db = isolated_database
        wallet = cast(
            WalletTypeInfo,
            SimpleNamespace(wallet=SimpleNamespace(id="test-wallet")),
        )
        request = cast(
            Request,
            SimpleNamespace(
                url=SimpleNamespace(netloc="example.com"),
                url_for=lambda _name, **_kwargs: "https://example.com/lnurl",
            ),
        )
        try:
            await migrate_old_schema(db)
            await migrations.m005_public_period_badge(db)
            created = await views_api.api_create_goal(
                goal_data(show_period_badge=visible), wallet
            )
            assert created.show_period_badge is visible
            response = Response()
            public = await views_api.api_public_goal(created.id, request, response)
            assert public.show_period_badge is visible
            assert response.headers["Cache-Control"] == "no-store"
            assert public.recurring is True
            assert "wallet" not in public.dict()

            await db.execute(
                "UPDATE zapgoals.goals SET current_amount = 117, period_index = 2 "
                "WHERE id = :id",
                {"id": created.id},
            )
            for value in (not visible, visible):
                saved = await views_api.api_update_goal(
                    created.id,
                    GoalData(**{**created.dict(), "show_period_badge": value}),
                    wallet,
                )
                reloaded = await crud.get_goal(saved.id)
                assert reloaded is not None
                assert reloaded.show_period_badge is value
                assert saved.current_amount == reloaded.current_amount == 117
                assert saved.period_index == reloaded.period_index == 2
                assert reloaded.recurrence_unit == "month"
                assert reloaded.recurrence_interval == created.recurrence_interval
                assert reloaded.target_date == created.target_date
                assert reloaded.target_wallet_id == "test-target"
                public = await views_api.api_public_goal(saved.id, request, Response())
                assert public.show_period_badge is value
                assert public.period_index == 2
                assert (await views_api.api_list_goals(wallet))[
                    0
                ].show_period_badge is value

            stranger = cast(
                WalletTypeInfo,
                SimpleNamespace(wallet=SimpleNamespace(id="another-wallet")),
            )
            with pytest.raises(HTTPException) as exc:
                await views_api.api_update_goal(created.id, goal_data(), stranger)
            assert exc.value.status_code == 403
        finally:
            await db.engine.dispose()

    asyncio.run(check())


def test_period_badge_default_and_api_schema():
    assert goal_data().show_period_badge is True
    assert goal_data(show_period_badge=False).show_period_badge is False
    app = FastAPI()
    app.include_router(zapgoals_ext)
    schemas = app.openapi()["components"]["schemas"]
    for model in ("GoalData", "Goal", "PublicGoal"):
        field = schemas[model]["properties"]["show_period_badge"]
        assert field["type"] == "boolean"
        assert field["default"] is True
