{
    "name": "Configurable Scorecards",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "summary": "Calculate scores from configured dimensions and classify subjects into bands",
    "description": "Provides scorecard, dimension and band records plus abstract subject, score-line and catalog mixins. Supports measured and catalog-based observations and queued refresh helpers. Consuming addons implement subject observations and classifications; the engine evaluates configured weights rather than supplying a universal predictive model.",
    "author": "AgroMarin",
    "website": "https://agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "base",
    ],
    "data": [
        "security/res_groups_security.xml",
        "security/ir.access.csv",
        "data/ir_job_channel_data.xml",
        "views/scorecard_views.xml",
        "views/scoring_menus.xml",
    ],
}
