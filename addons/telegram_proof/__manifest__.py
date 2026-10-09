{
    "name": "Telegram Proof of Identity",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Let a contact confirm a record with a button in their own Telegram chat, or prove it is them with a code sent there",
    "description": "Adds two proof methods for people bound to a Telegram bot. Telegram Confirmation: a contact asked to confirm a record (a customer who paid a collector) receives in their own private chat with the bot what they confirm, with Confirm and Not right buttons; the button pressed in that chat, on that message, by the account still bound to that contact, is their answer, and the others are withdrawn. After Not right, what they write next is passed on to the record. Telegram Code: a six-digit code sent to the signer's chat, with what they agree to, which the user who asks them enters; for a user, their own chat. Only a chat whose account is bound to the contact (an invitation, a session) reaches them: a stand-in contact created by a stranger's first message is not the customer. The evidence records the chat, the message and how and when the account was bound, and who invited it, so a binding made at the door by the person asking stands out.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "proof",
        "telegram",
    ],
    "data": [
        "data/proof_method_data.xml",
    ],
    "auto_install": True,
}
