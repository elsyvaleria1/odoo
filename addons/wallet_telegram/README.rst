Wallets over Telegram
====================

Linked internal users can consult their own card or TAG balances with
``/saldo`` and request a top-up with ``/recarga`` in a private chat.
The commands work with fuel, toll and other wallet accounts.

Configuration
-------------

* Install ``wallet_telegram`` and add its two commands to the existing bot.
* Select the wallet accounts served by that bot. They must belong to its
  configured companies.
* Set each card's holder to the contact of the internal Odoo user who carries
  it. The user's Telegram account must already be linked through the bot's
  standard verification process.
* Configure a top-up approval category on each wallet account. Use a category
  for manual requests, require the amount and define the responsible
  approvers. An empty category permits balance consultation only.
* To deliver approval notifications through Telegram, configure the existing
  ``approval_telegram`` bot and approval-step notification settings. Approvers
  need linked private chats too. Its normal company routing applies.

Behavior
--------

When several cards are assigned, the user selects one from a paginated list.
The balance includes the date of the last observation saved by the issuer
connector; these commands do not refresh it. Without an observation, the bot
reports that a balance is unavailable, even if another module computes a
local accounting balance for that card.

A top-up request collects a positive amount, respecting the currency's
precision, and a reason. The user confirms before a native approval request
is created and submitted under their own permissions. The account, card and
reason are recorded on the request. Category restrictions and native approval
rules remain in force. Approval does not transfer money or reload a card.

The bot rechecks the user's binding, command permission, company, configured
accounts, card holder and approval category before submitting. Buttons belong
to one conversation flow; cancellation and replay do not create a second
request. ``/cancelar`` uses the bot's standard flow cancellation.

Validation
----------

The module's router tests use synthetic wallets and users, with Telegram
delivery mocked. They cover holder isolation, company guards, missing issuer
balances, fuel and toll accounts together, confirmation and replay, revoked
access, category denial and amount validation.
