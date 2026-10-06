============
Telegram Bot
============

This module provides the core infrastructure for integrating Telegram bots with Odoo.

Features
========

* Telegram Bot API wrapper (``sendMessage``, ``sendDocument``, ``getFile``,
  ``answerCallbackQuery``, ``editMessageReplyMarkup``) on top of ``integration``
* Webhook handler at ``/telegram/webhook/<bot_token>`` with
  ``X-Telegram-Bot-Api-Secret-Token`` verification
* Duplicate-update handling through the integration receiver, with cached API
  responses reused during supported handler retries. This is not a universal
  exactly-once delivery guarantee.
* Command routing with three-tier permission model (unlinked, partner,
  internal user), where "internal" excludes portal and other share users
* Base commands: ``/start``, ``/ayuda``, ``/quiensoy``
* Chat session state machine with per-chat rate limiting (token bucket via
  ``rate_limit``) and context storage for multi-step flows
* Markdown helpers that escape interpolated values, so a partner name carrying
  ``_``, ``*``, ``` ` ``` or ``[`` cannot make Telegram reject the message
* Automatic partner linking by Telegram username, case- and ``@``-insensitive
* Inbound/outbound message history with per-chat ``msg_uid`` deduplication,
  15-day auto-vacuum for delivered traffic and 90-day for failures
* Inline keyboard support (buttons with ``callback_data``)
* Log filter that masks bot tokens in werkzeug output

Configuration
=============

1. Create (or reuse) a ``credential.credential`` record with service
   ``telegram`` and the bot token in ``bearer_token``.
2. Go to Telegram > Telegram Bots and create a bot referencing that
   credential.
3. **Press Register Webhook on the bot form.** It generates a random 32-byte
   secret, stores it as the webhook receiver's credential and registers
   ``https://<your-odoo>/telegram/webhook/<bot_token>`` with Telegram, passing
   that secret as ``secret_token``. Without a secret the bot token in the
   webhook URL is the only credential, and that URL is written verbatim to
   every proxy access log the request passes through; anyone who can read one
   can post forged updates.
4. A bot that existed before secrets were enforced is flagged
   ``legacy_secretless_webhook`` and its updates are still accepted without
   one (the form warns about it). Register Webhook gives it a secret and ends
   that.
5. Add the commands the bot should answer under Telegram > Configuration >
   Commands and link them on the bot. A handler registered in Python that is not
   linked to the bot answers "comando desconocido".

Usage
=====

This is a base module that other ``telegram_bot_*`` modules depend on to add
domain-specific functionality (attendance, approval automation, financial
reports, project tasks).

Send a message programmatically:

.. code-block:: python

    bot = env['telegram.bot'].search([('name', '=', 'My Bot')], limit=1)
    bot.send_message(chat_id='123456', text='Hello from Odoo!')

Pass ``parse_mode=None`` for text built from untrusted values, or run the values
through the Markdown helpers:

.. code-block:: python

    md = bot.get_markdown_helpers()
    bot.send_message(chat.chat_id, f"Hola {md['bold'](partner.name)}")

Extend with custom commands in a child module:

.. code-block:: python

    from odoo.addons.telegram.controllers.telegram_controller import (
        TelegramController,
    )

    class MyBotController(TelegramController):
        def __init__(self):
            super().__init__()
            self._command_handlers['/status'] = '_handle_status_command'
            self._partner_added_cmds.add('/status')

        def _handle_status_command(self, bot, chat, args, partner=False, internal_user=False):
            bot.send_message(chat.chat_id, f'Hello {partner.name}!')

Writing a handler
=================

A handler runs inside a savepoint. If it raises, its database work is rolled
back, the conversation is reset to ``idle`` and the user is told — so a crash
cannot strand someone mid-flow.

What is *not* rolled back is anything already sent to Telegram. Odoo re-runs a
whole endpoint on a serialisation conflict, so keep the outbound calls to the
model's methods (``send_message``, ``send_document``, ``get_file_content`` …):
they go through the replay guard and a re-run reuses the first answer. A raw
``requests`` call from a handler will happen once per attempt.

Bug Tracker
===========

Bugs are tracked on GitHub Issues. In case of trouble, please check there
if your issue has already been reported.

Credits
=======

Authors
~~~~~~~

* AgroMarin
