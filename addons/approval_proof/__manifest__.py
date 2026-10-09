{
    "name": "Approval Decisions Proven by Identity",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Require a proof of identity bound to a request's figures before an approver's approval or refusal counts",
    "description": "Adds to each approval category which decisions need a proof of identity (none, approvals, or approvals and refusals) and which proof methods are accepted. On such a category, an approver deciding from the request's form or from their approval activity is shown the figures they decide on and asked for a proof (a passkey, or another accepted method); the proof covers the request, the decision, the approver's row and the source document's protected fields, and is refused if any of them moved meanwhile. A decision arriving without a proof (bulk decisions, marking the activity done, Telegram, a direct call) is refused. Each proven decision's log row links the evidence. Categories requiring a proof cannot auto-approve by consent.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "approval",
        "proof",
    ],
    "data": [
        "security/ir.access.csv",
        "views/approval_category_views.xml",
        "views/approval_request_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "approval_proof/static/src/**/*",
        ],
        "web.assets_tests": [
            "approval_proof/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
