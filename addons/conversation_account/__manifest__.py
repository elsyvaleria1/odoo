{
    "name": "Conversations - Accounting",
    "version": "19.0.1.1.0",
    "category": "Sales/CRM",
    "sequence": 68,
    "summary": "Add a conversation tool that creates draft customer invoices",
    "description": "Registers an approval-configured accounting tool in the conversation catalog. It resolves a customer, parses the supplied invoice lines and creates a customer invoice in draft with an origin link to the conversation. Accounting users must review and post the resulting invoice; this addon supplies the tool definition, not transcription.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "conversation",
        "account",
    ],
    "data": [
        "data/conversation_tools.xml",
    ],
    "auto_install": True,
}
