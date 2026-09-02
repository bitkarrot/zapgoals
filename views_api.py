from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
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
    delete_goal_and_contributions,
    get_goal,
    get_goal_by_username,
    get_goals,
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


@zapgoals_api_router.get(
    "/goals",
    response_model=list[Goal],
    summary="List wallet goals",
    description="Returns ZapGoals owned by the wallet identified by an invoice key.",
)
async def api_list_goals(
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Goal]:
    return await get_goals(wallet.wallet.id)


@zapgoals_api_router.post(
    "/goals",
    response_model=Goal,
    status_code=HTTPStatus.CREATED,
    summary="Create a goal",
    description="Creates a ZapGoal for the wallet identified by an admin key.",
)
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


@zapgoals_api_router.put(
    "/goals/{goal_id}",
    response_model=Goal,
    summary="Update a goal",
    description="Updates an owned goal without changing its wallet or settled total.",
)
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


@zapgoals_api_router.delete(
    "/goals/{goal_id}",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Delete a goal",
    description=(
        "Deletes an owned goal and its extension tracking rows. "
        "LNbits wallet payment history is retained."
    ),
)
async def api_delete_goal(
    goal_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
) -> None:
    goal = await get_goal(goal_id)
    if not goal:
        raise _not_found()
    _check_owner(goal, wallet)
    await delete_goal_and_contributions(goal.id)


@zapgoals_api_router.get(
    "/goals/{goal_id}/public",
    response_model=PublicGoal,
    summary="Get public goal state",
    description=(
        "Returns public presentation settings, settled satoshi total, target, "
        "deadline, and payment identifiers for alternate frontends."
    ),
)
async def api_public_goal(
    goal_id: str, request: Request, response: Response
) -> PublicGoal:
    goal = await get_goal(goal_id)
    if not goal:
        raise _not_found()
    response.headers["Cache-Control"] = "no-store"
    return public_goal(goal, request)


@zapgoals_api_router.post(
    "/goals/{goal_id}/invoice",
    response_model=InvoiceResponse,
    status_code=HTTPStatus.CREATED,
    summary="Create a contribution invoice",
    description=(
        "Creates a 10-minute BOLT11 invoice for a public goal. Amount is in "
        "satoshis; the optional comment is limited to 280 characters. Expired "
        "unpaid tracking rows are cleaned up before issuance."
    ),
)
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
    "/lnurl/{goal_id}",
    response_model=LnurlPayResponse,
    name="zapgoals_lnurl",
    summary="Get an LNURL-pay request",
    description=(
        "Returns public LNURL-pay metadata for a goal. Sendable amounts are "
        "expressed in millisatoshis by the LNURL protocol."
    ),
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
    summary="Request an LNURL-pay invoice",
    description=(
        "Creates a goal invoice from an LNURL-pay callback. The amount query "
        "parameter is in millisatoshis. A valid NIP-57 kind 9734 event may be "
        "provided through the nostr parameter."
    ),
)
async def api_lnurl_callback(
    goal_id: str,
    request: Request,
    amount: int = Query(..., description="Invoice amount in millisatoshis."),
    comment: str | None = Query(
        None, description="Optional LNURL-pay comment, up to 280 characters."
    ),
    nostr: str | None = Query(
        None, description="Optional JSON-encoded NIP-57 kind 9734 zap request."
    ),
    lnurl: str | None = Query(
        None, description="Optional bech32 LNURL associated with the zap request."
    ),
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
    "/well-known/{username}",
    response_model=LnurlPayResponse | LnurlErrorResponse,
    summary="Resolve a goal Lightning Address",
    description=(
        "Internal target for /.well-known/lnurlp/{username}. It is active only "
        "when ZapGoals owns the LNbits Lightning Address redirect."
    ),
)
async def api_well_known(username: str, request: Request):
    normalized = username.strip().lower()
    goal = await get_goal_by_username(normalized)
    if not goal:
        return LnurlErrorResponse(reason="Lightning address not found")
    identifier = f"{goal.lightning_address_username}@{request.url.netloc}"
    return await make_lnurl_response(goal, request, identifier)
