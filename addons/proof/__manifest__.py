{
    "name": "Proof of Identity for Recorded Acts",
    "version": "19.0.1.2.0",
    "category": "Hidden",
    "summary": "Bind a user's approval of a record to a one-time proof of identity and keep it as chained evidence",
    "description": "A module that needs a person to vouch for a record (an approval, a handover) issues a one-time challenge covering the record's figures. The user answers it with a proof method, and the accepted proof is stored as evidence: who, which record, which figures, which method, when and from where. Evidence rows cannot be changed or deleted, and each one carries a SHA-256 hash chained to the previous row, so a changed row, or a removed row that later proofs were chained after, is detected. Methods answered with a one-time code sent to the signer's own channel (email, Telegram) share one core: the challenge keeps only an HMAC of the code, under the database secret, and five wrong codes spend it, counted outside the request so a refused code still counts. Ships the password method and the dialog that shows the user what they vouch for and collects the proof; other methods (passkeys) come from their own modules. A contact with no user account (a customer) can also confirm a record on their own channel: the contact confirmation mixin sends them what they are asked to confirm, every channel module that reaches them carries it, and they answer Confirm or Not right there, by a link to a page that answers only on a POST, or in the channel itself; the first answer is chained as evidence with its verdict and the other messages are withdrawn. Unanswered requests are reminded once and expire. With the contact at the counter, a code they receive is the fallback. Consuming modules decide which acts require a proof and which records their contacts confirm.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "data": [
        "security/proof_security.xml",
        "security/ir.access.csv",
        "data/proof_method_data.xml",
        "data/ir_cron_data.xml",
        "views/proof_answer_templates.xml",
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
