{
    "name": "Conversations - Phone Calls",
    "version": "19.0.3.0.0",
    "category": "Productivity/Conversations",
    "summary": "File every recorded phone call on a conversation, whatever line carried it",
    "description": "Files a phone call's recordings on a conversation instead of on the call, so a call from the softphone, the phone system or a company handset is analysed, and its business actions proposed, the same way. The conversation names the call's contact, responsible user, number and the name the line knew the contact by, and follows the call when a late call-log entry completes it.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "conversation",
        "phone_call",
    ],
    "data": [
        "views/conversation_conversation_views.xml",
        "views/phone_call_views.xml",
    ],
    "auto_install": True,
}
