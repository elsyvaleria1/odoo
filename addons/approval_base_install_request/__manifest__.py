{
    "name": "Module Install Request Approvals",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Route module activation requests through approval before installation review",
    "description": "Creates approval requests for module activation and opens the installation dependency review only after approval. Uses the supplied activation category and forbids self-approval in its installation hook. An administrator must explicitly continue installation; the approval decision does not install the module.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "approval",
        "base_install_request",
    ],
    "data": [
        "data/approval_category_data.xml",
        "views/base_module_install_request_views.xml",
    ],
    "auto_install": True,
    "post_init_hook": "_forbid_self_approval",
}
