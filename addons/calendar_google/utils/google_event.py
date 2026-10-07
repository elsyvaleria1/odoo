import re
from collections import abc
from collections.abc import Iterator

from odoo.libs.json import dumps as json_dumps
from odoo.tools import email_normalize

from odoo.addons.calendar.tools.event_mapping import prepare_event_mapping


class GoogleEvent(abc.Set):
    """This helper class holds the values of a Google event.
    Inspired by Odoo recordset, one instance can be a single Google event or a
    (immutable) set of Google events.
    All usual set operations are supported (union, intersection, etc).

    A list of all attributes can be found in the API documentation.
    https://developers.google.com/calendar/v3/reference/events#resource

    :param iterable: iterable of GoogleCalendar instances or iterable of dictionnaries

    """

    def __init__(self, iterable=()) -> None:
        self._events = prepare_event_mapping(self.__class__, iterable)

    def __iter__(self) -> Iterator[GoogleEvent]:
        return iter(GoogleEvent([vals]) for vals in self._events.values())

    def __contains__(self, google_event) -> bool:
        return google_event.id in self._events

    def __len__(self) -> int:
        return len(self._events)

    def __bool__(self) -> bool:
        return bool(self._events)

    def __getattr__(self, name):
        # check_singleton
        try:
            (_event,) = self._events.keys()
        except ValueError as e:
            raise ValueError("Expected singleton: %s" % self) from e
        event_id = next(iter(self._events.keys()))
        value = self._events[event_id].get(name)
        json_dumps(value)
        return value

    def __repr__(self) -> str:
        return "%s%s" % (self.__class__.__name__, self.ids)

    @property
    def ids(self):
        return tuple(e.id for e in self)

    @property
    def rrule(self):
        if self.recurrence and any("RRULE" in item for item in self.recurrence):
            return next(item for item in self.recurrence if "RRULE" in item)
        return None

    def _meta_odoo_id(self, dbname) -> int | None:
        """Returns the Odoo id stored in the Google Event metadata.
        This id might not actually exists in the database.
        """
        properties = (
            self.extendedProperties
            and (
                self.extendedProperties.get("shared", {})
                or self.extendedProperties.get("private", {})
            )
        ) or {}
        o_id = properties.get("%s_odoo_id" % dbname)
        if o_id:
            return int(o_id)
        return None

    def owner(self, env):
        # Owner/organizer could be desynchronised between Google and Odoo.
        # Let userA, userB be two new users (never synced to Google before).
        # UserA creates an event in Odoo (they are the owner) but userB syncs first.
        # There is no way to insert the event into userA's calendar since we don't have
        # any authentication access. The event is therefore inserted into userB's calendar
        # (they are the organizer in Google). The "real" owner (in Odoo) is stored as an
        # extended property. There is currently no support to "transfert" ownership when
        # userA syncs their calendar the first time.
        real_owner_id = self.extendedProperties and self.extendedProperties.get(
            "shared", {}
        ).get("%s_owner_id" % env.cr.dbname)
        try:
            # If we create an event without user_id, the event properties will be 'false'
            # and python will interpret this a a NoneType, that's why we have the 'except TypeError'
            real_owner_id = int(real_owner_id)
        except ValueError, TypeError:
            real_owner_id = False
        real_owner = (real_owner_id and env["res.users"].browse(real_owner_id)) or env[
            "res.users"
        ]
        if real_owner_id and real_owner.exists():
            return real_owner
        elif self.organizer and self.organizer.get("self"):
            return env.user
        elif self.organizer and self.organizer.get("email"):
            # In Google: 1 email = 1 user; but in Odoo several users might have the same email :/
            org_email = email_normalize(self.organizer.get("email"))
            return env["res.users"].search(
                [("email_normalized", "=", org_email)], limit=1
            )
        else:
            return env["res.users"]

    def filter(self, func) -> GoogleEvent:
        return GoogleEvent(e for e in self if func(e))

    def is_recurrence(self) -> bool:
        return bool(self.recurrence)

    def is_recurrent(self) -> bool:
        return bool(self.recurringEventId or self.is_recurrence())

    def is_cancelled(self) -> bool:
        return self.status == "cancelled"

    def is_recurrence_follower(self) -> bool:
        return bool(not self.originalStartTime or self.originalStartTime == self.start)

    def full_recurring_event_id(self) -> str | None:
        """
        Give the complete identifier with elements
        in `id` and `recurringEventId`.
        :return: concatenation of the id created by the recurrence
                and the id created by the modification of a specific event
        :rtype: string if recurrent event and correct ids, `None` otherwise
        """
        # Regex expressions to match elements (according to the google support [not documented]):
        # - ID: [a-zA-Z0-9]+
        # - RANGE: R[0-9]+T[0-9]+
        # - TIMESTAMP: [0-9]+T[0-9]+Z
        # With:
        # - id: 'ID_TIMESTAMP'
        # - recurringEventID: 'ID_RANGE'
        # Find: 'ID_RANGE_TIMESTAMP'
        if not self.is_recurrent():
            return None
        # Check if ids are the same
        id_value = re.match(r"(\w+_)", self.id)
        recurringEventId_value = re.match(r"(\w+_)", self.recurringEventId)
        if (
            not id_value
            or not recurringEventId_value
            or id_value.group(1) != recurringEventId_value.group(1)
        ):
            return None
        rec_pattern = re.search(r"(\w+_R\d+(?:T\d+)?(?:Z)?)", self.recurringEventId)
        if not rec_pattern:
            return None
        id_range = rec_pattern.group()

        ts_pattern = re.search(r"(\d{8}(?:T\d+Z?)?)$", self.id)
        if not ts_pattern:
            return None
        timestamp = ts_pattern.group()

        return f"{id_range}_{timestamp}"

    def get_meeting_url(self):
        if not self.conferenceData:
            return False
        video_meeting = list(
            filter(
                lambda entryPoints: entryPoints.get("entryPointType") == "video",
                self.conferenceData.get("entryPoints", []),
            )
        )
        return video_meeting[0].get("uri") if video_meeting else False

    def is_available(self) -> bool:
        return self.transparency == "transparent"
