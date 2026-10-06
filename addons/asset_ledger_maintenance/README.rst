==========================
Asset Maintenance Plans
==========================

Preventive and corrective maintenance management for equipment tracked as product assets (lot/serial numbers).

**Table of contents**

.. contents::
   :local:

Features
========

Maintenance Plans
-----------------

A plan is core Maintenance's ``maintenance.plan`` on an asset, extended here:

* **Interval-based scheduling**: every N days, weeks, months or years
* **Counted from completion**: by default the next request falls one interval after
  the day the last one came back; a plan can count on fixed dates instead
* **One open request**: the plan always holds its next request, ahead of time
* **Distance trigger**: a plan can also fall due by odometer, read off the asset's meter
* **Archive to pause**: an archived plan opens no request; unarchiving resumes it
* **Compliance metrics**: completed vs cancelled requests
* **Conflict detection**: alerts when several plans fall due the same day

Maintenance Plan Templates
--------------------------

Standardize maintenance across similar equipment:

* **Reusable templates**: Define interval, duration, and instructions once
* **Mass application**: Apply templates to multiple equipment via wizard
* **Asset type filtering**: Templates can target specific asset types (vehicle, equipment, machinery)

Maintenance Requests
--------------------

A request is core Maintenance's ``maintenance.order`` on an asset. The stock
transfers are only the equipment's trip to the workshop and back:

* **Send to Maintenance**: creates the transfer to the warehouse's maintenance location
* **Stages follow the transfers**: validating the outgoing transfer puts the request in
  progress; validating its return closes it
* **Equipment validation**: the return must bring back the equipment that was sent
* **Vendor tracking**: the supplier performing external maintenance
* **Return metrics**: planned end vs actual return, and the delay

Equipment State Tracking
------------------------

Know where your assets are at any moment:

* **Operational states**:

  - *In Storage*: Available in warehouse
  - *Deployed*: In operational use at field/site
  - *In Maintenance*: Under repair

* **Maintenance health**:

  - *Good*: No open request due
  - *Warning*: A preventive request is due or under way
  - *Critical*: A corrective request is open

Warehouse Configuration
-----------------------

Enable maintenance and deployment per warehouse:

* **Maintenance operations**:

  - Dedicated maintenance location (``WH/Maintenance``)
  - Maintenance picking type with sequences
  - Maintenance return picking type

* **Deployment operations**:

  - Dedicated deployed location (``WH/Deployed``)
  - Deployment picking type
  - Deployment return picking type

Asset Log Integration
---------------------

Automatic history tracking:

* Creates ``resource.asset.log`` entries when maintenance is completed
* Records maintenance type, duration, vendor, and timing metrics
* Links logs to the originating maintenance request

Configuration
=============

1. **Enable maintenance in warehouse**:

   Go to *Inventory > Configuration > Warehouses*, edit your warehouse,
   and check "Allow Maintenance". This creates the maintenance location
   and picking types automatically.

2. **Enable deployment (optional)**:

   In the same warehouse form, check "Allow Deployment" to enable
   equipment deployment tracking.

3. **Mark products for maintenance**:

   On the product form, enable "Recurring Maintenance" under the
   Maintenance tab. This allows lot/serial numbers of this product
   to have maintenance plans.

4. **Create maintenance templates**:

   Go to *Maintenance > Configuration > Plan Templates* to create
   reusable maintenance schedules.

Usage
=====

Creating a Maintenance Plan
---------------------------

1. Open the asset, or *Maintenance > Maintenance Plans*
2. Select a template or set the interval, how it counts, and the first occurrence
3. Save: the plan opens its first request on that date

Manual Maintenance Request
--------------------------

1. From the asset form, click "Request a Maintenance"
2. Fill in the maintenance details (type, duration, vendor)
3. Click "Send to Maintenance" to move the equipment to the maintenance location
4. When the work is done, return the transfer to bring the equipment back;
   validating the return closes the request and logs the service

Scheduled Maintenance
---------------------

A daily cron sends out every plan's open order that is due by date or by odometer,
creating one transfer, carrying every serial of the order, through the assets' warehouse. A second daily cron refreshes the
plan and asset states that depend on the date.

Dependencies
============

* ``asset_ledger``: Base asset tracking functionality
* ``maintenance``: the order and the plan, which maintain resources and the assets on them

Technical Notes
===============

* Uses Odoo's native ``return_ids`` field for tracking return pickings
* Location flags (``maintenance_location``, ``deployed_location``) are mutually exclusive
* Up to version 19.0.1.11.0 the request was a ``stock.picking``; the 19.0.1.12.0 migration
  turns each such picking into a ``maintenance.order`` and links the picking and its
  return to it

Contributors
============

* AgroMarin Development Team

Maintainer
==========

This module is maintained by AgroMarin.
