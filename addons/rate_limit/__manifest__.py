{
    "name": "Request Rate Limits",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Apply configured request-rate limits to supported service entry points",
    "description": "Provides reusable rate-limit accounting and configuration for callers that explicitly invoke the limiter. Installing it does not automatically limit every route.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "base",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_cron.xml",
        "views/rate_limit_bucket_views.xml",
        "views/rate_limit_menus.xml",
    ],
}
