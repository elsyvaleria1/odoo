
from datetime import datetime

from odoo.libs.datetime import timezone


def prepare_ics_file(
    *,
    created_at: datetime,
    start: datetime,
    end: datetime,
    timezone_name: str,
    name: str,
    description: str,
    location: str | None = None,
) -> bytes:
    import vobject

    calendar = vobject.iCalendar()
    event = calendar.add("vevent")
    event.add("created").value = created_at.replace(tzinfo=timezone("UTC"))
    event.add("dtstart").value = start.astimezone(timezone(timezone_name))
    event.add("dtend").value = end.astimezone(timezone(timezone_name))
    event.add("summary").value = name
    event.add("description").value = description
    if location is not None:
        event.add("location").value = location
    serialized: str = calendar.serialize()
    return serialized.encode("utf-8")
