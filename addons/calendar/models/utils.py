import uuid

from odoo.libs.intervals import Intervals


def generate_calendar_token():
    return uuid.uuid4().hex


def interval_from_events(event_ids):
    return Intervals(
        [
            (event.start, event.stop, event)
            for event in event_ids
            if event.start and event.stop
        ]
    )
