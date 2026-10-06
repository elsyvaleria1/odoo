{
    "name": "emSigner Signer Identification",
    "version": "1.0",
    "category": "Sales/Sign",
    "summary": "Offer emSigner identification during document signing when IAP credits are available",
    "description": "Adds emSigner (Aadhaar eSign) as a signer-role authentication method through IAP. The signed document is accepted only when its eSign signature verifies, chains to the CCA India 2022 roots and was appended to the exact document sent for that signer's attempt; the certificate's name is recorded as the signer. Requires service access and IAP credits. If the account has fewer than one credit, the implementation permits signing without the additional identification and records signed_without_extra_auth.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sign",
        "iap",
    ],
    "data": [
        "data/iap_service_data.xml",
        "reports/sign_emsigner_log_reports.xml",
        "views/sign_request_templates.xml",
    ],
    "assets": {
        "sign.assets_public_sign": [
            "sign_emsigner/static/src/components**/*",
            "sign_emsigner/static/src/dialogs**/*",
        ],
        "web.assets_backend": [
            "sign_emsigner/static/src/**/*",
        ],
        "web.assets_frontend": [
            "sign_emsigner/static/src/components**/*",
            "sign_emsigner/static/src/dialogs**/*",
        ],
    },
}
