import asyncio
from unittest.mock import AsyncMock

from .. import crud


def test_purge_removes_only_expired_unpaid_goal_contributions(monkeypatch):
    execute = AsyncMock()
    monkeypatch.setattr(crud.db, "execute", execute)

    asyncio.run(crud.purge_expired_unpaid_contributions("goal123", 600))

    execute.assert_awaited_once()
    execute_call = execute.await_args
    assert execute_call is not None
    query, values = execute_call.args
    assert "goal_id = :goal_id" in query
    assert "paid = false" in query
    assert "created_at <" in query
    assert values["goal_id"] == "goal123"
