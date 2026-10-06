{
    "name": "Conversations - Sales",
    "version": "19.0.1.1.0",
    "category": "Sales/CRM",
    "sequence": 66,
    "summary": "Add a conversation tool that creates draft sales quotations",
    "description": "Registers a sales tool with a leader approval category. Resolves the named customer or conversation contact and creates a draft quotation from supplied lines, with unresolved products represented as notes. Links the quotation origin to the conversation; sales users review the resulting quantities and products before confirmation.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "conversation",
        "sale",
    ],
    "data": [
        "data/conversation_tools.xml",
    ],
    "auto_install": True,
}
