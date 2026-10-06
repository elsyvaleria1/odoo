{
    "name": "itsme Signer Identification",
    "version": "1.0",
    "category": "Sales/Sign",
    "summary": "Offer itsme identification during document signing when IAP credits are available",
    "description": "Not installable. The itsme® IAP proxy reports a signer's identity in a callback that carries nothing this database can verify: the signer's own link token and an unkeyed sha256 of the reported name and birthdate. Anyone holding the signing link could therefore record any identity as verified by itsme®. The module stays uninstallable until the proxy signs its answer with a key the database holds, or lets the database fetch the verified result itself.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sign",
        "iap",
    ],
    "data": [
        "data/iap_service_data.xml",
        "reports/sign_itsme_log_reports.xml",
        "views/sign_request_templates.xml",
    ],
    "assets": {
        "sign.assets_public_sign": [
            "sign_itsme/static/src/**/*",
        ],
        "web.assets_backend": [
            "sign_itsme/static/src/**/*",
        ],
        "web.assets_frontend": [
            "sign_itsme/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "sign_itsme/static/tests/itsme_dialog.test.js",
        ],
    },
    "installable": False,
}
