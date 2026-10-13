{
    "name": "Document Exchange Framework",
    "version": "19.0.1.0.3",
    "oldest_upgradable_version": "19.0.1.0.1",
    "category": "Hidden",
    "sequence": 6,
    "summary": "Track document transmission intents and counterparty responses",
    "description": "Provides exchange channels, transmission records, a protocol interface and a mixin for business documents. Keeps business acceptance or rejection separate from transport results. Concrete protocol addons supply document preparation and counterparty operations; connections require the relevant credentials and configuration.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "integration",
        "certificate",
    ],
    "data": [
        "security/ir_access.xml",
        "security/ir.access.csv",
        "views/exchange_channel_views.xml",
        "views/exchange_transmission_views.xml",
        "views/exchange_menus.xml",
        "data/ir_cron.xml",
    ],
}
