from http import HTTPStatus
from io import BytesIO

import pyqrcode
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
    get_due_recurring_goals,
    get_goal,
    get_goal_by_username,
    get_goals,
    get_periods,
    update_goal,
)
from .models import (
    MAX_SATS,
    SCHEDULER_CRONS,
    Goal,
    GoalData,
    InvoiceRequest,
    InvoiceResponse,
    Period,
    PublicGoal,
    SchedulerSetupData,
    SweepError,
)
from .ratelimit import WindowRateLimiter
from .services import (
    COMMENT_ALLOWED,
    create_goal_invoice,
    lnurl_metadata,
    make_lnurl_response,
    public_goal,
    sweep_recurring_goal,
    validate_zap_request,
)
from .settings import invoice_rate_limit_per_minute

zapgoals_api_router = APIRouter(prefix="/api/v1")

_invoice_limiter = WindowRateLimiter(invoice_rate_limit_per_minute)


def _rate_limit_key(request: Request, goal_id: str) -> str:
    client = request.client
    host = client.host if client else "unknown"
    return f"{host}:{goal_id}"


def _not_found():
    return HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Goal not found")


def _check_owner(goal: Goal, wallet: WalletTypeInfo) -> None:
    if goal.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your goal")


def _scheduler_jobs(payload) -> list[dict]:
    if isinstance(payload, list):
        return [job for job in payload if isinstance(job, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "results"):
            jobs = payload.get(key)
            if isinstance(jobs, list):
                return [job for job in jobs if isinstance(job, dict)]
    return []


def _scheduler_frequency(schedule: str | None) -> str | None:
    for frequency, cron in SCHEDULER_CRONS.items():
        if schedule == cron:
            return frequency
    return None


def _scheduler_jobs_matching(jobs: list[dict]) -> list[dict]:
    return [
        job
        for job in jobs
        if str(job.get("url", "")).endswith("/zapgoals/api/v1/recurring/sweep-due")
        or (
            "zapgoals" in str(job.get("name", "")).lower()
            and "zapgoalswasm" not in str(job.get("url", ""))
        )
    ]


def _scheduler_job(jobs: list[dict]) -> dict | None:
    return next(iter(_scheduler_jobs_matching(jobs)), None)


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
        "unpaid tracking rows are cleaned up before issuance. Invoice creation "
        "is limited per client and goal per minute."
    ),
)
async def api_goal_invoice(
    goal_id: str, request: Request, data: InvoiceRequest
) -> InvoiceResponse:
    goal = await get_goal(goal_id)
    if not goal:
        raise _not_found()
    if not _invoice_limiter.allow(_rate_limit_key(request, goal_id)):
        raise HTTPException(
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            detail="Too many invoices requested for this goal; try again shortly",
        )
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
        "provided through the nostr parameter. Invoice creation is limited "
        "per client and goal per minute."
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
    if not _invoice_limiter.allow(_rate_limit_key(request, goal_id)):
        return LnurlErrorResponse(
            reason="Rate limit exceeded; please wait a minute before requesting "
            "another invoice"
        )
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
    "/qr",
    response_class=Response,
    summary="QR code for a Lightning invoice",
    description=(
        "Renders an SVG QR code used by the embeds for BOLT11 invoices. "
        "Only payloads that start with LIGHTNING: are accepted, so the "
        "endpoint cannot be used to generate arbitrary QR codes."
    ),
)
def api_qr(
    data: str = Query(..., description="QR payload; must start with LIGHTNING:")
) -> Response:
    payload = data.strip()
    if not payload.upper().startswith("LIGHTNING:") or len(payload) > 2000:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Only LIGHTNING: QR payloads are supported",
        )
    code = pyqrcode.create(payload, error="M")
    stream = BytesIO()
    code.svg(stream, scale=4)
    return Response(
        content=stream.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=600"},
    )


@zapgoals_api_router.post(
    "/goals/{goal_id}/sweep",
    response_model=Period,
    summary="Sweep a recurring goal",
    description=(
        "Manually triggers a period-end sweep for a recurring goal. Moves "
        "settled sats to the target wallet, records a period ledger row, "
        "and advances the goal to the next period. The goal must be "
        "recurring and its target_date must be in the past."
    ),
)
async def api_sweep_goal(
    goal_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
) -> Period:
    goal = await get_goal(goal_id)
    if not goal:
        raise _not_found()
    _check_owner(goal, wallet)
    try:
        return await sweep_recurring_goal(goal_id)
    except SweepError as exc:
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=str(exc)) from exc


@zapgoals_api_router.post(
    "/recurring/sweep-due",
    response_model=list[Period],
    summary="Sweep all due recurring goals",
    description=(
        "Sweeps every recurring goal owned by the wallet whose period has "
        "ended. Intended as the target for a scheduled HTTP call (e.g. "
        "the LNbits scheduler extension firing hourly). Each goal is swept "
        "independently; failures for one goal do not block the others."
    ),
)
async def api_sweep_due(
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> list[Period]:
    due = await get_due_recurring_goals(wallet.wallet.id)
    results: list[Period] = []
    for goal in due:
        try:
            period = await sweep_recurring_goal(goal.id)
            results.append(period)
        except SweepError as exc:
            from loguru import logger

            logger.warning("Sweep failed for goal {}: {}", goal.id, str(exc))
    return results


@zapgoals_api_router.get(
    "/recurring/scheduler-status",
    response_model=dict,
    summary="Check sweep scheduler status",
    description=(
        "Reports whether automatic sweeps are enabled via the built-in "
        "fallback loop or the scheduler extension, and whether a "
        "zapgoals sweep job already exists in the scheduler."
    ),
)
async def api_scheduler_status(
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> dict:
    from .settings import (
        builtin_scheduler_enabled,
        builtin_scheduler_interval_seconds,
    )

    status: dict = {
        "builtin_scheduler": builtin_scheduler_enabled,
        "builtin_scheduler_interval_seconds": builtin_scheduler_interval_seconds,
        "scheduler_extension": False,
        "scheduler_job_exists": False,
        "scheduler_frequency": None,
        "scheduler_job_id": None,
    }
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://localhost:5000/scheduler/api/v1/jobs",
                headers={"X-Api-Key": wallet.wallet.adminkey},
                timeout=5,
            )
            if resp.status_code == 200:
                status["scheduler_extension"] = True
                job = _scheduler_job(_scheduler_jobs(resp.json()))
                if job:
                    status["scheduler_job_exists"] = True
                    status["scheduler_job_id"] = job.get("id")
                    status["scheduler_frequency"] = _scheduler_frequency(
                        job.get("schedule")
                    )
    except Exception:
        pass
    return status


@zapgoals_api_router.post(
    "/recurring/setup-scheduler",
    response_model=dict,
    summary="Create a scheduler extension job for recurring sweeps",
    description=(
        "Creates or updates a scheduler extension cron job that checks for "
        "due goals. The check frequency can be hourly, every six hours, "
        "daily, or weekly; goals are only swept after their configured period ends. "
        "Requires the scheduler extension to be installed."
    ),
)
async def api_setup_scheduler(
    data: SchedulerSetupData,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    import httpx

    schedule = SCHEDULER_CRONS[data.frequency]
    payload = {
        "name": "ZapGoals recurring sweep",
        "status": True,
        "selectedverb": "POST",
        "url": "http://localhost:5000/zapgoals/api/v1/recurring/sweep-due",
        "headers": [{"key": "X-Api-Key", "value": wallet.wallet.adminkey}],
        "body": "",
        "schedule": schedule,
        "extra": None,
    }
    try:
        async with httpx.AsyncClient() as client:
            jobs_response = await client.get(
                "http://localhost:5000/scheduler/api/v1/jobs",
                headers={"X-Api-Key": wallet.wallet.adminkey},
                timeout=10,
            )
            existing = None
            duplicates = []
            if jobs_response.status_code == 200:
                matching = _scheduler_jobs_matching(
                    _scheduler_jobs(jobs_response.json())
                )
                existing = matching[0] if matching else None
                duplicates = matching[1:]

            for duplicate in duplicates:
                await client.delete(
                    f"http://localhost:5000/scheduler/api/v1/jobs/{duplicate['id']}",
                    headers={"X-Api-Key": wallet.wallet.adminkey},
                    timeout=10,
                )

            if existing:
                payload["id"] = existing["id"]
                resp = await client.put(
                    f"http://localhost:5000/scheduler/api/v1/jobs/{existing['id']}",
                    headers={"X-Api-Key": wallet.wallet.adminkey},
                    json=payload,
                    timeout=10,
                )
                action = "updated"
            else:
                resp = await client.post(
                    "http://localhost:5000/scheduler/api/v1/jobs",
                    headers={"X-Api-Key": wallet.wallet.adminkey},
                    json=payload,
                    timeout=10,
                )
                action = "created"
            if resp.status_code in (200, 201):
                return {
                    "success": True,
                    "action": action,
                    "frequency": data.frequency,
                    "job": resp.json(),
                }
            return {
                "success": False,
                "detail": f"Scheduler returned {resp.status_code}: {resp.text}",
            }
    except Exception as exc:
        return {"success": False, "detail": str(exc)}


@zapgoals_api_router.get(
    "/goals/{goal_id}/periods",
    response_model=list[Period],
    summary="List period history for a recurring goal",
    description=(
        "Returns the per-period ledger for a recurring goal, ordered by "
        "period index ascending. Each row records the zapped total, amount "
        "moved to the target wallet, rollover, and sweep timestamp."
    ),
)
async def api_goal_periods(
    goal_id: str, wallet: WalletTypeInfo = Depends(require_invoice_key)
) -> list[Period]:
    goal = await get_goal(goal_id)
    if not goal:
        raise _not_found()
    _check_owner(goal, wallet)
    return await get_periods(goal_id)


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
