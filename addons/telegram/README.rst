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
* Base commands: ``/start``, ``/ayuda``, ``/quiensoy``, ``/desconectar``,
  ``/cancelar``
* Chat session state machine with per-chat rate limiting (token bucket via
  ``rate_limit``) and context storage for multi-step flows
* Telegram HTML helpers (``tools/format.py``) that escape interpolated values,
  so a partner name carrying ``<`` or ``&`` cannot make Telegram reject the
  message
* Identity by proof, never by username: a ``telegram.account`` acts as someone
  only through an active ``telegram.binding``, made by consuming a single-use
  link token that an Odoo session or an administrator's invitation minted
* A verified phone number per account, recorded when its owner shares their
  own contact (the contact's ``user_id`` is the sender's): what Telegram
  vouches for, never what someone types
* An outbox: messages are queued (``_queue_text``, ``_queue_file``,
  ``_queue_phone_request``) and sent by a job after the transaction commits,
  each exactly once or visibly not; a chat records when Telegram starts
  refusing what is sent to it (``delivery_failed_at``) until a send goes
  through again
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

This is a base module that other ``*_telegram`` modules depend on to add
domain-specific functionality (attendance, approvals, financial reports,
project tasks, Discuss).

Queue a message: it is sent after the transaction commits, and its
``telegram.message`` row records what became of it.

.. code-block:: python

    bot = env['telegram.bot'].search([('name', '=', 'My Bot')], limit=1)
    bot._queue_text(chat, 'Hello from Odoo!', html=False)

Telegram HTML built from values goes through ``tools/format.py``, which
escapes them:

.. code-block:: python

    from odoo.addons.telegram.tools import format as tg
    bot._queue_text(chat, f"Hola {tg.bold(partner.name)}")

Extend with a handler in a child module: an abstract model named
``telegram.handler.<feature>`` inheriting ``mixin.telegram.handler``. The
router finds it in the registry; what it answers is what it declares.

.. code-block:: python

    from odoo import models
    from odoo.addons.telegram.tools.dispatch import TelegramCommand

    class TelegramHandlerStatus(models.AbstractModel):
        _name = "telegram.handler.status"
        _inherit = "mixin.telegram.handler"
        _description = "Telegram: Status"

        def _telegram_commands(self):
            return {"/estado": TelegramCommand("_handle_status_command", "partner")}

        def _handle_status_command(self, bot, chat, args, partner=False, internal_user=False):
            bot._queue_text(chat, f"Hola {partner.name}", html=False)

Besides commands, buttons and messages, a handler hears what happens around
them; each hook is a no-op by default, and these reach every handler, enabled
on the bot or not:

* ``_on_account_bound(bot, chat, binding)`` -- someone just proved who they
  are through ``/start <token>``;
* ``_on_phone_verified(bot, chat, account)`` -- someone shared their own
  number, now ``account.phone``;
* ``_on_bot_membership(bot, chat, status)`` -- the bot was blocked, unblocked,
  added or removed.

``telegram.message._on_delivery_failed(error, started)`` is the outbox's: a
queued send Telegram refused for good, ``started`` saying whether its chat was
delivering until then. A refused edit or deletion is no delivery failure.

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
