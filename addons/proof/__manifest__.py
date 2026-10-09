{
    "name": "Proof of Identity for Recorded Acts",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Bind a user's approval of a record to a one-time proof of identity and keep it as chained evidence",
    "description": "A module that needs a person to vouch for a record (an approval, a handover) issues a one-time challenge covering the record's figures. The user answers it with a proof method, and the accepted proof is stored as evidence: who, which record, which figures, which method, when and from where. Evidence rows cannot be changed or deleted, and each one carries a SHA-256 hash chained to the previous row, so a changed row, or a removed row that later proofs were chained after, is detected. Ships the password method and the dialog that shows the user what they vouch for and collects the proof; other methods (passkeys) come from their own modules. Consuming modules decide which acts require a proof.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "web",
    ],
    "data": [
        "security/proof_security.xml",
        "security/ir.access.csv",
        "data/proof_method_data.xml",
        "views/proof_method_views.xml",
        "views/proof_evidence_views.xml",
        "views/proof_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "proof/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "proof/static/tests/**/*",
        ],
    },
}
