{
    "name": "Phone Calls",
    "version": "19.0.1.0.0",
    "category": "Productivity/Phone",
    "summary": "Keep one record per phone call, whichever line or device carried it",
    "description": "Defines the phone call every telephony source files on: the softphone, a phone system and a company handset. Holds the number, direction, outcome, timing, contact, responsible user and company, matches the number to a contact of that company, and files the call's recordings on its timeline for transcription. Placing, receiving and recording calls belong to the addons that drive a line.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "phone_validation",
        "speech",
    ],
    "data": [
        "security/ir.access.csv",
        "views/phone_call_views.xml",
        "views/res_partner_views.xml",
    ],
}
