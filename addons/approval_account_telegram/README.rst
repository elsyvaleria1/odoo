=====================================
Telegram Bot Approval Account
=====================================

This module extends telegram_bot to add payment approval request
management features through Telegram.

**Table of contents**

.. contents::
   :local:

Features
========

* Multi-step payment approval workflow (details → proof → confirmation)
* File handling (photos, PDFs) for payment proof
* Partner validation and CFDI use resolution
* Bank statement line linking
* Automatic accounting operation creation on approval
* State management for chat sessions

Commands
--------

* ``/pago`` - Start payment registration workflow
* ``/cancelarpago`` - Cancel current payment workflow

Configuration
=============

Configure your Telegram bot in the Telegram Bot settings and ensure
the approval workflow is properly set up.

Usage
=====

1. Send ``/pago`` to start a new payment registration
2. Follow the prompts to enter payment details
3. Upload payment proof (photo or PDF)
4. Confirm the payment details
5. The approval request will be created automatically

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
