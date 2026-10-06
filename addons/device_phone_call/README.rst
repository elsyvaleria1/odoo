==================
Device Phone Calls
==================

Company handsets and the phone system as ``device.device`` endpoints that report
their calls. The module description in ``__manifest__.py`` covers what the call
and recording routes store; this file covers the part a device has to agree
with — what each route *answers*, and what the device does with it. Both routes
answer under ``/remote/device/<identifier>/`` and, for the handsets already in
the field, ``/remote/mobile/<identifier>/``; ``device_mobile`` adds the location
route beside them.

The handset client is the ``odoo-companion`` app, a sibling checkout at
``../../odoo-companion``. Its ``README.md`` is the other half of this contract
and states the request side: payload shapes, units, and the outbox that holds a
record until one of the answers below releases it.

**The contract is deployed on real phones.** A handset in the field talks to
whatever Odoo it points at, which is not necessarily one running this revision.
A change here has to leave an older build behaving no worse than before.

What each route answers
=======================

The two batch routes answer with three counts, and they mean three different
things:

``accepted``
   Rows newly stored.

``duplicates``
   Rows this device had already sent, dropped by ``_remove_already_stored`` on
   (device, start, number, direction, outcome) for calls and (device, timestamp,
   coordinates) for fixes. **A delivery that happened twice, not a loss.**

``skipped``
   Rows read and not storable — no number, no coordinates, a direction this
   module cannot map to anything.

``skipped_indexes``
   Which of those, as indexes into the batch as posted. Without it the phone
   could only delete the whole batch on a partial skip, refused rows included.
   Every reply also carries ``"service": "remote_mobile"``, so a phone can tell
   this endpoint from a gateway answering in its place.

The status code follows from the first two::

    200   accepted or duplicates    the batch is accounted for
    422   neither                   nothing here was storable
    400   the body is not readable as this route's payload

Why the duplicate count exists
------------------------------

It used to be folded into ``skipped``, and the status came from ``accepted > 0``
alone. Both counts are taken *after* the already-stored rows are dropped, so
"nothing here was storable" and "I already hold every row" left the same empty
recordset and the same **422** — which the phone reads as a refusal. It
dead-lettered call records this database was holding, and counted them on the
handset's status screen as records that could not be delivered.

Two layers of deduplication sit under this, and only the first is visible to the
transport:

* ``integration`` matches the **payload hash** within
  ``duplicate_window_seconds`` and answers **409**. The phone counts a duplicate
  and removes the row. Correct, and the common case.
* Past that window the request looks new, so the **model** dedup catches it
  instead. That is the case the 422 got wrong — and it is not exotic: the
  companion's periodic upload runs on a fifteen-minute period, which is exactly
  the 900-second default window, a Wi-Fi-only device waits hours, and
  WorkManager's backoff passes 900 s at its sixth retry.

The recording route has its second layer too: ``_stored_device_recording``
recognises a file this device already sent by its name and write time, and the
route answers 200 with the stored ``recording_id`` and ``"duplicates": 1``.
Without it a retry past the window filed the audio twice.

An Android call type newer than this module
-------------------------------------------

``CALL_TYPES`` maps the types ``CallLog.Calls.TYPE`` can hold onto a direction
and an outcome (``missed`` is an incoming call that was not answered). One it
does not know is stored with the ``unknown`` outcome rather than dropped, because dropping it
made the entry unusable — and a batch carrying nothing else answered 422, so the
handset dead-lettered a call that had happened.

That is the same loss adding ``ANSWERED_EXTERNALLY_TYPE`` to the table was meant
to end, one layer down and waiting for the next type Android defines. Only a raw
*number* falls back this way. A word this module does not recognise is a payload
defect, not a platform version, and is still skipped.

A recording ahead of its call-log entry
---------------------------------------

The handset uploads a recording as soon as the dialer closes the file, which is
often before the call log that dates and directs the call. Such a recording
makes a call of its own, ``awaits_call_log``, transcribed only after a grace
period; the entry, when it arrives, completes that call instead of making a
second one, and its transcription starts at once. The recording reply says
``matched`` when the call was already there.

Provisioning
============

A device in the **Mobile Phone** or **Phone System** category is created with
``duplicate_detection_enabled``, a 900-second window, and a payload cap sized for
call audio. One created without it gets neither deduplication layer nor the cap —
and the small default cap answers 413 to every recording. Setting the category is
part of provisioning, not a cosmetic field.

Testing
=======

.. code-block:: bash

    odoo-bin -d <db> -u device_phone_call,device_mobile --test-enable \
        --test-tags '/device_phone_call,/device_mobile'

``../../odoo-companion/tools/smoke-test.sh <url> <identifier> <token>`` replays
the payloads a handset actually sends against a live instance, including the
duplicate and unknown-type cases above.
