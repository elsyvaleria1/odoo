======================
Telegram Bot Digest
======================

Send Odoo digest reports via Telegram using the existing ``telegram_bot`` infrastructure.

Overview
--------

Extends Odoo's digest system to send KPI reports via Telegram messages instead of
(or in addition to) email. Leverages the existing ``telegram_bot`` module for all
Telegram communication.

Features
--------

- Uses existing ``telegram_bot`` infrastructure (no direct Telegram dependency)
- Replace email entirely or send both Telegram + Email
- Bot resolved automatically from the user's registered chat
- Explicit bot override configurable per digest
- Markdown V1 escaping for safe rendering of dynamic values
- Automatic fallback to email when Telegram fails in replace mode
- Test send button to verify configuration

Dependencies
------------

- ``telegram_bot`` — Core Telegram infrastructure
- ``digest`` — Base digest functionality

Configuration
-------------

1. Go to **Telegram Bot → Bots** and ensure a bot is configured.
2. Go to **Telegram Bot → Chats** and link each recipient's partner to a chat.
3. Open a digest (**Settings → Technical → Email → Digests**).
4. Go to the **Telegram** tab.
5. Enable *Send via Telegram*.
6. Choose *Send Mode* (Replace or Complement Email).
7. Click **Send Test Message to Me** to verify.

Send Modes
----------

Replace Email (Telegram Only)
  Sends only via Telegram. Falls back to email if Telegram fails.

Complement Email (Both)
  Sends via both Telegram and Email.

Bot Resolution
--------------

When no explicit bot is configured on the digest, the bot that originally
registered the user's ``telegram.chat`` record is used automatically. This
prevents Telegram API errors from bot/chat mismatches.

Credits
-------

Author
  AgroMarin

License
  0BSD (Zero-Clause BSD; see LICENSE.addons at the repository root)
