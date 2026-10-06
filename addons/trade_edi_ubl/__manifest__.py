{
    "name": "Trade UBL Order Infrastructure",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Build and decode UBL order documents for adopting trade models",
    "description": "Adds shared UBL order-node construction and import helpers over trade accounting and UBL/CII dependencies. Extends the order mixin with builder selection and uploaded-document decoding hooks. Concrete order integrations supply their direction-specific fields; this addon does not itself transmit documents over Peppol.",
    "author": "Odoo Community",
    "website": "https://www.odoo.com",
    "license": "LGPL-3",
    "depends": [
        "trade_account",
        "account_edi_ubl_cii",
    ],
    "auto_install": True,
}
