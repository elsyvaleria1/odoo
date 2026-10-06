==============================
Telegram Bot Approval Request
==============================

Approver side of the Telegram approvals flow. When an ``approval.request``
reaches an approver, the bot **pushes** it to their chat and lets them
**approve**, **request changes** or **refuse** (with a comment) straight from
inline buttons — no slash commands. Browsing all pending requests is handled by
a **Mini App** (web view) opened from the bot's chat menu button.

Complementary to ``approval_ai_telegram`` (the requester side, which
creates the request from natural language / voice). Together they move the full
approval round-trip to Telegram.

How it works
============

- **Push** — ``approval.approver._create_activity`` is extended; whenever an
  approver becomes *pending* (initial submit or a sequential-chain promotion),
  ``telegram.approval.notifier`` resolves the approver's linked
  ``telegram.chat`` (on a bot with **Notify Approval Requests** enabled) and
  sends a summary with inline buttons.
- **Approve** — one tap → ``approval.request.action_approve(approver=...)``,
  attributed to the real approver.
- **Refuse** — pick a reason (``approval.refusal.reason`` for the category) +
  optional comment → writes ``refusal_reason_id`` / ``refusal_note`` →
  ``action_refuse(skip_wizard=True)``.
- **Request changes** — pick the field (date / description) + comment →
  ``action_request_change(skip_wizard=True, requested_change_field=...)``; the
  comment is posted to the owner's chatter.
- **Mini App** — ``/telegram/approval/app/<bot_id>`` serves a page authenticated
  with Telegram WebApp ``initData`` (HMAC-SHA256 against the bot token); it
  lists the approver's pending requests.

Identity is resolved through the chat's ``partner_id → user_ids``; only linked
internal users can decide. Decisions run on the existing ``approval.request``
(no public links, no ``quick_approve`` revival).

Setup
=====

1. Enable **Notify Approval Requests** on the approval bot
   (``telegram.bot``).
2. Link each approver's ``res.partner.telegram_username`` and have them open
   the bot once so a ``telegram.chat`` is created.
3. Point the bot's chat menu button to
   ``<web.base.url>/telegram/approval/app/<bot_id>`` for the Mini App.

Task: t22525.
