{
    "name": "UBL and CII Invoices",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Import and export electronic invoices using supported UBL and CII formats",
    "description": "Provides XML import and export builders for the supported UBL and CII invoice formats, including Peppol BIS, XRechnung, NLCIUS, E-FFF and Factur-X. Adds invoice attachments and format-specific PDF packaging through the invoice sending workflow. Format selection and output depend on partner, company and invoice data; network delivery and additional jurisdiction-specific rules are supplied by their respective addons.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "external_dependencies": {
        "python": [
            "python-stdnum",
        ],
        "apt": {
            "python-stdnum": "python3-stdnum",
        },
    },
    "data": [
        "data/cii_22_templates.xml",
        "views/account_tax_views.xml",
        "views/res_partner_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_edi_ubl_cii/static/src/scss/**/*",
        ],
    },
    "auto_install": True,
    "uninstall_hook": "uninstall_hook",
}
