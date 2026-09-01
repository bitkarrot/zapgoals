from fastapi import APIRouter, Depends
from lnbits.core.views.generic import index, index_public
from lnbits.decorators import check_account_id_exists

zapgoals_generic_router = APIRouter()

zapgoals_generic_router.add_api_route(
    "/",
    methods=["GET"],
    endpoint=index,
    dependencies=[Depends(check_account_id_exists)],
)

zapgoals_generic_router.add_api_route(
    "/{goal_id}", methods=["GET"], endpoint=index_public
)
