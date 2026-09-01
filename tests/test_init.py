from fastapi import APIRouter

from .. import zapgoals_ext


def test_router_can_be_included():
    router = APIRouter()
    router.include_router(zapgoals_ext)
