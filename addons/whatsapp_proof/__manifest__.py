{
    "name": "WhatsApp Proof of Identity",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Let a contact confirm a record with a button on a WhatsApp message to their own number",
    "description": "Adds the WhatsApp Confirmation proof method: a contact asked to confirm a record (a customer who paid a collector, who received a delivery, who signs a document) receives on their own WhatsApp number what they confirm, with two quick-reply buttons, the first confirming, the second saying it is not right. The button pressed in reply to that message, from that number, is their answer. The message is an approved template of the WhatsApp account, chosen on the method: model Proof Confirmation Message, a body whose first free-text variable is the company and second what the contact confirms, and the two quick replies in that order. Until such a template is set and approved, the method reaches nobody. WhatsApp's authentication templates cannot state an amount, so no code is sent this way.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "proof",
        "whatsapp",
    ],
    "data": [
        "data/proof_method_data.xml",
        "views/proof_method_views.xml",
    ],
    "auto_install": True,
}
