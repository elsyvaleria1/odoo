=======================
Company Phone Telemetry
=======================

Company-owned Android phones as ``device.device`` endpoints of the **Mobile
Phone** category, running the ``odoo-companion`` app. This module stores the
locations a handset posts to ``/remote/mobile/<identifier>/location``; its call
log and recordings go to ``device_phone_call``, whose ``README.rst`` states the
contract every route answers on — counts, status codes, deduplication and
provisioning.

A phone's **Phone Number** is its SIM's, as the carrier issued it. It is keyed
by its last ten digits (``phone_call``'s ``number_key``), so ``+52 1 55 …`` and
``55 …`` are one number, and no two active phones share one.
``device_mobile_telegram`` matches it to the number a Telegram account shared,
to tell the Telegram of a company phone from any other.
