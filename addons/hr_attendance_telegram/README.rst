======================
Telegram Bot Attendance
======================

This module extends telegram_bot to add employee attendance management
features through Telegram.

**Table of contents**

.. contents::
   :local:

Features
========

* Check-in/check-out with optional time override
* Lunch break tracking (lunch out/lunch in)
* Automatic workorder stopping on checkout
* Timezone-aware time parsing
* Daily auto-checkout cron for open attendances

Commands
--------

* ``/entrada`` - Clock in
* ``/salida`` - Clock out
* ``/comida`` - Start lunch break
* ``/regresocomida`` - End lunch break

Configuration
=============

No specific configuration is required. The module uses the Telegram bot
configuration from the base ``telegram_bot`` module.

Usage
=====

Employees can use Telegram commands to manage their attendance:

1. Send ``/entrada`` to clock in
2. Send ``/comida`` to start lunch break
3. Send ``/regresocomida`` to end lunch break
4. Send ``/salida`` to clock out

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
