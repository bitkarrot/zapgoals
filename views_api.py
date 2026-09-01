from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from lnbits.core.models import WalletTypeInfo
from lnbits.decorators import require_admin_key, require_invoice_key
from lnurl import (
    LightningInvoice,
    LnurlErrorResponse,
    LnurlPayActionResponse,
    LnurlPayResponse,
)
from pydantic import parse_obj_as

from .crud import (
    create_goal,
    delete_goal_and_unpaid_contributions,
    get_goal,
    get_goal_by_username,
    get_goals,
    has_paid_contributions,
    update_goal,
)
from .models import (
    MAX_SATS,
    Goal,
    GoalData,
    InvoiceRequest,
    InvoiceResponse,
    PublicGoal,
)
from .services import (
    COMMENT_ALLOWED,
    create_goal_invoice,
    lnurl_metadata,
    make_lnurl_response,
    public_goal,
    validate_zap_request,
)

zapgoals_api_router = APIRouter(prefix="/api/v1")


def _not_found():
    return HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Goal not found")


def _check_owner(goal: Goal, wallet: WalletTypeInfo) -> None:
    if goal.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your goal")


@zapgoals_api_router.get("/goals", response_model=list[Goal])
async def api_list_goals(
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Goal]:
    return await get_goals(wallet.wallet.id)


@zapgoals_api_router.post("/goals", response_model=Goal, status_code=HTTPStatus.CREATED)
async def api_create_goal(
    data: GoalData, wallet: WalletTypeInfo = Depends(require_admin_key)
) -> Goal:
    if data.lightning_address_username:
        existing = await get_goal_by_username(data.lightning_address_username)
        if existing:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Lightning address username is already in use",
            )
    return await create_goal(wallet.wallet.id, data)


@zapgoals_api_router.put("/goals/{goal_id}", response_model=Goal)
async def api_update_goal(
    goal_id: str,
    data: GoalData,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> Goal:
    goal = await get_goal(goal_id)
    if not goal:
        raise _not_found()
    _check_owner(goal, wallet)
    if data.lightning_address_username:
        existing = await get_goal_by_username(data.lightning_address_username)
        if existing and existing.id != goal.id:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Lightning address username is already in use",
            )
    return await update_goal(goal, data)


@zapgoals_api_router.delete("/goals/{goal_id}", status_code=HTTPStatus.NO_CONTENT)
async def api_delete_goal(
    goal_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
) -> None:
    goal = await get_goal(goal_id)
    if not goal:
        raise _not_found()
    _check_owner(goal, wallet)
    if await has_paid_contributions(goal.id):
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail="Goals with paid contributions cannot be deleted",
        )
    await delete_goal_and_unpaid_contributions(goal.id)


@zapgoals_api_router.get("/goals/{goal_id}/public", response_model=PublicGoal)
async def api_public_goal(goal_id: str, request: Request) -> PublicGoal:
    goal = await get_goal(goal_id)
    if not goal:
        raise _not_found()
    return public_goal(goal, request)


@zapgoals_api_router.post("/goals/{goal_id}/invoice", response_model=InvoiceResponse)
async def api_goal_invoice(goal_id: str, data: InvoiceRequest) -> InvoiceResponse:
    goal = await get_goal(goal_id)
    if not goal:
        raise _not_found()
    try:
        extra = {"comment": data.comment} if data.comment else None
        return await create_goal_invoice(goal, data.amount, "invoice", extra=extra)
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Unable to create invoice"
        ) from exc


@zapgoals_api_router.get(
    "/lnurl/{goal_id}", response_model=LnurlPayResponse, name="zapgoals_lnurl"
)
async def api_lnurl(goal_id: str, request: Request) -> LnurlPayResponse:
    goal = await get_goal(goal_id)
    if not goal:
        raise _not_found()
    return await make_lnurl_response(goal, request)


@zapgoals_api_router.get(
    "/lnurl/cb/{goal_id}",
    response_model=LnurlPayActionResponse | LnurlErrorResponse,
    name="zapgoals_lnurl_callback",
)
async def api_lnurl_callback(
    goal_id: str,
    request: Request,
    amount: int = Query(...),
    comment: str | None = Query(None),
    nostr: str | None = Query(None),
    lnurl: str | None = Query(None),
):
    goal = await get_goal(goal_id)
    if not goal:
        return LnurlErrorResponse(reason="Goal not found")
    if amount < 1000 or amount > MAX_SATS * 1000 or amount % 1000:
        return LnurlErrorResponse(
            reason="Amount must be a whole number of sats between 1 and 2100000000"
        )
    if len(comment or "") > COMMENT_ALLOWED:
        return LnurlErrorResponse(
            reason=f"Comment exceeds {COMMENT_ALLOWED} characters"
        )

    source = "lnurl"
    extra = {}
    if comment:
        extra["comment"] = comment
    identifier = (
        f"{goal.lightning_address_username}@{request.url.netloc}"
        if goal.lightning_address_username
        else f"{goal.id}@{request.url.netloc}"
    )
    description = lnurl_metadata(goal, identifier).encode()
    if nostr:
        try:
            _, relays = validate_zap_request(nostr, goal, amount)
        except ValueError as exc:
            return LnurlErrorResponse(reason=str(exc))
        source = "nostr"
        description = nostr.encode()
        extra.update({"nostr": nostr, "nostr_relays": relays})
        if lnurl:
            extra["lnurl"] = lnurl
    try:
        invoice = await create_goal_invoice(
            goal,
            amount // 1000,
            source,
            unhashed_description=description,
            extra=extra,
        )
    except Exception:
        return LnurlErrorResponse(reason="Unable to create invoice")
    payment_request = parse_obj_as(LightningInvoice, invoice.payment_request)
    return LnurlPayActionResponse(pr=payment_request, routes=[])


@zapgoals_api_router.get(
    "/well-known/{username}", response_model=LnurlPayResponse | LnurlErrorResponse
)
async def api_well_known(username: str, request: Request):
    normalized = username.strip().lower()
    goal = await get_goal_by_username(normalized)
    if not goal:
        return LnurlErrorResponse(reason="Lightning address not found")
    identifier = f"{goal.lightning_address_username}@{request.url.netloc}"
    return await make_lnurl_response(goal, request, identifier)
