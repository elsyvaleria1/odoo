{
    "name": "GitHub API Client",
    "version": "19.0.1.2.0",
    "oldest_upgradable_version": "19.0.1.1.0",
    "category": "Hidden",
    "sequence": 10,
    "summary": "Provide GitHub REST calls, App installation tokens, and pull request and check state kept current by webhook",
    "description": "Supplies client helpers for repositories, branches, commits, webhooks, issues, pull requests and reviews, plus a GraphQL query method. Seeds a GitHub integration service and uses the shared transport and credential records. Adds check run, commit status, workflow run, compare and branch calls; mints GitHub App installation tokens limited to named repositories from an app credential; and receives signed webhook deliveries that keep pull requests and the checks of their head commit current, for other modules to follow. Calling addons must provide credentials with permissions for the requested GitHub operation.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "integration",
        "mail",
    ],
    "data": [
        "security/ir.access.csv",
        "data/api_service_data.xml",
        "data/credential_category_data.xml",
        "data/credential_category_field_data.xml",
        "views/integration_github_views.xml",
        "views/integration_github_menus.xml",
    ],
}
