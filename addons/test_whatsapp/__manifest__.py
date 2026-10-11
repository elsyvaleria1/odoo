{
    "name": "Whatsapp Tests",
    "version": "1.0",
    "category": "Hidden",
    "sequence": 9898,
    "summary": "Test Whatsapp behaviour, including discuss channel, tour, whatsapp composer",
    "description": "Run regression tests for Whatsapp. Loaded test suites include ``DiscussChannel``, ``TestWhatsappTours``, ``WhatsAppComposerRendering``, ``WhatsAppComposerSending``, ``WhatsAppMessage``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "partner",
        "mail",
        "portal",
        "whatsapp",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_tests": [
            "test_whatsapp/static/tests/tours/**/*",
        ],
    },
}
