======================
Telegram Bot Financial
======================

This module extends telegram_bot to add financial reporting features
through Telegram.

**Table of contents**

.. contents::
   :local:

Features
========

* Partner Ledger PDF generation and delivery
* Date range parsing (defaults to current year)
* Partner transaction validation
* Company-specific report generation
* Interactive period selection with inline keyboards

Commands
--------

* ``/estadoctapropio`` - Generate the requester's own partner ledger report for
  the current year
* ``/estadocuentaperiodo`` - Select period interactively:

  - Ultimo mes (previous complete month)
  - Ultimos 3 meses (last 3 complete months)
  - Ultimo semestre (last 6 complete months)
  - Año anterior (previous calendar year)
  - Personalizado (custom date range)

* ``/edocliente`` - (**linked employees only**) Query the account statement of
  any client. Starts an interactive flow:

  1. Type part of the client name to search; every client with posted
     receivable lines in LMMR matches, people as well as companies
  2. Select the client from the results
  3. Select the period (same options as ``/estadocuentaperiodo`` plus "Año actual")
  4. Receive the PDF statement

  Requires a linked internal user, whatever their groups: the commercial area
  asks for its clients' statements. A chat linked to a client gets that
  client's own statement only.

Configuration
=============

No specific configuration is required. The module uses the Telegram bot
configuration from the base ``telegram_bot`` module.

The statement reads receivable accounts only, so its balance at today's date
is the client's Due. Access to other clients follows the chat's linked
partner: an internal user reads any client, anyone else only their own
statement. The report log still records whether the requester was an
accounting manager.

Usage
=====

1. Send ``/estadoctapropio`` to receive your account statement for the current year
2. Send ``/estadocuentaperiodo`` to select a specific period interactively
3. Send ``/edocliente`` (linked employees only) to query any client's account
   statement

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/AgroMarin/agromarin-addons/issues>`_.

Credits
=======

Authors
-------

* AgroMarin

Contributors
------------

* AgroMarin Development Team

Maintainers
-----------

This module is maintained by AgroMarin.
