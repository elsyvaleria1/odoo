=======================
Company Phone Telemetry
=======================

Company-owned Android phones as ``device.device`` endpoints of the **Mobile
Phone** category, running the ``odoo-companion`` app. This module stores the
locations a handset posts to ``/remote/mobile/<identifier>/location``; its call
log and recordings go to ``device_phone_call``, whose ``README.rst`` states the
contract every route answers on — counts, status codes, deduplication and
provisioning.
