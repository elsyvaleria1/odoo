{
    "name": "Conversations - Purchasing",
    "version": "19.0.1.1.0",
    "category": "Sales/CRM",
    "sequence": 65,
    "summary": "Add a conversation tool that creates draft purchase quotations",
    "description": "Registers a purchase tool with a leader approval category. Resolves the named supplier or conversation contact, requires catalog products for the supplied lines and creates a draft request for quotation with conversation origin and optional delivery date. Purchasing reviews and confirms the result through the normal order workflow.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "conversation",
        "purchase",
    ],
    "data": [
        "data/conversation_tools.xml",
    ],
    "auto_install": True,
}
