from fastapi import FastAPI

from .. import zapgoals_ext


def test_openapi_exposes_only_api_and_protocol_routes():
    app = FastAPI()
    app.include_router(zapgoals_ext)
    schema = app.openapi()
    paths = schema["paths"]

    assert "/zapgoals/" not in paths
    assert "/zapgoals/{goal_id}" not in paths
    assert paths["/zapgoals/api/v1/goals/{goal_id}/public"]["get"]["summary"] == (
        "Get public goal state"
    )
    assert (
        paths["/zapgoals/api/v1/goals/{goal_id}/invoice"]["post"]["summary"]
        == "Create a contribution invoice"
    )
    assert (
        paths["/zapgoals/api/v1/lnurl/cb/{goal_id}"]["get"]["parameters"][1][
            "description"
        ]
        == "Invoice amount in millisatoshis."
    )


def test_openapi_documents_amount_units_and_invoice_expiry():
    app = FastAPI()
    app.include_router(zapgoals_ext)
    schema = app.openapi()
    schemas = schema["components"]["schemas"]

    assert schemas["GoalData"]["properties"]["goal_amount"]["description"] == (
        "Funding target in satoshis."
    )
    assert schemas["InvoiceRequest"]["properties"]["amount"]["description"] == (
        "Contribution amount in satoshis."
    )
    invoice_operation = schema["paths"]["/zapgoals/api/v1/goals/{goal_id}/invoice"][
        "post"
    ]
    assert invoice_operation["responses"].get("201")
    assert "10-minute" in invoice_operation["description"]
