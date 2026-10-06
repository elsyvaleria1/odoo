==========================
Telegram on Company Phones
==========================

Bridges ``device_mobile`` and ``mail_telegram``. A bot delivering Odoo
notifications gets **Only to Company Phones**: when set, a user's notifications,
replies to them and the inbox inside Telegram reach only a Telegram account that
is a company phone of theirs.

A company phone of a user is an active ``device.device`` of the **Mobile Phone**
category whose *Phone user* they are, in the bot's company or in none. A
Telegram account is that phone's when the number its owner shared with a bot
(``telegram.account.phone``, which Telegram vouches for) is the phone's number:
both are compared in E.164, the phone's read in its company's country when
written without a country code. An account registered before Mexico dropped the
mobile ``1`` (``+52 1 55 …``) is the same line as ``55 …``.

Rolling it out
==============

1. Record each phone's number and phone user under Devices.
2. Set Only to Company Phones on the bot.
3. Each employee, on the phone, presses Connect Telegram in My Preferences and
   then shares the phone's number when the bot asks (or presses Share Phone
   Number in Telegram in Preferences later). Preferences says whether their
   notifications are delivered, and why not.

Telegram never says when an account's number changes: the owner shares it
again. The device form shows, to administrators, the Telegram account of the
phone's number and who it acts as.
