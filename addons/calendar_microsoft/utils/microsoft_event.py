from collections import abc
from collections.abc import Iterator

from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.tools import email_normalize

from odoo.addons.calendar.tools.event_mapping import prepare_event_mapping

_debug = DebugLog(__name__)


class MicrosoftEvent(abc.Set):
    """
    This helper class holds the values of a Microsoft event.
    Inspired by Odoo recordset, one instance can be a single Microsoft event or a
    (immutable) set of Microsoft events.
    All usual set operations are supported (union, intersection, etc).

    :param iterable: iterable of MicrosoftCalendar instances or iterable of dictionnaries
    """

    def __init__(self, iterable=()) -> None:
        self._events = prepare_event_mapping(self.__class__, iterable)

    def __iter__(self) -> Iterator[MicrosoftEvent]:
        return iter(MicrosoftEvent([vals]) for vals in self._events.values())

    def __contains__(self, microsoft_event) -> bool:
        return microsoft_event.id in self._events

    def __len__(self) -> int:
        return len(self._events)

    def __bool__(self) -> bool:
        return bool(self._events)

    def __getattr__(self, name):
        # check_singleton
        try:
            (event_id,) = self._events
        except ValueError:
            raise ValueError(f"Expected singleton: {self}") from None
        value = self._events[event_id].get(name)
        json_dumps(value)
        return value

    def __repr__(self) -> str:
        return "%s%s" % (self.__class__.__name__, self.ids)

    @property
    def ids(self):
        """
        Use 'id' to return an event identifier which is specific to a calendar
        """
        return tuple(e.id for e in self)

    @property
    def uids(self):
        """
        Use 'iCalUid' to return an identifier which is unique accross all calendars
        """
        return tuple(e.iCalUId for e in self)

    def owner_id(self, env):
        """
        Indicates who is the owner of an event (i.e the organizer of the event).

        There are several possible cases:
        1) the current Odoo user is the organizer of the event according to Outlook event, so return his id.
        2) the current Odoo user is NOT the organizer and:
           2.1) we are able to find a Odoo user using the Outlook event organizer email address and we use his id,
           2.2) we are NOT able to find a Odoo user matching the organizer email address and we return False, meaning
                that no Odoo user will be able to modify this event. All modifications will be done from Outlook.
        """
        if self.isOrganizer:
            return env.user.id

        if not self.organizer:
            return False

        organizer_email = self.organizer.get("emailAddress") and email_normalize(
            self.organizer.get("emailAddress").get("address")
        )
        if organizer_email:
            # Warning: In Microsoft: 1 email = 1 user; but in Odoo several users might have the same email
            user = env["res.users"].search([("email", "=", organizer_email)], limit=1)
            return user.id if user else False
        return False

    def filter(self, func) -> MicrosoftEvent:
        return MicrosoftEvent(e for e in self if func(e))

    def _filtered_series(self, series_master_id) -> MicrosoftEvent:
        return self.filter(lambda e: e.seriesMasterId == series_master_id)

    def is_recurrence(self) -> bool:
        return self.type == "seriesMaster"

    def is_recurrent(self) -> bool:
        return bool(self.seriesMasterId or self.is_recurrence())

    def is_recurrent_not_master(self) -> bool:
        return bool(self.seriesMasterId)

    def get_recurrence(self):
        if not self.recurrence:
            return {}
        pattern = self.recurrence["pattern"]
        range = self.recurrence["range"]
        repeat_type_dict = {
            "endDate": "until",
            "noEnd": "forever",
            "numbered": "count",
        }
        repeat_unit_dict = {
            "daily": "day",
            "weekly": "week",
            "absoluteMonthly": "month",
            "relativeMonthly": "month",
            "absoluteYearly": "year",
            "relativeYearly": "year",
        }
        index_dict = {
            "first": "1",
            "second": "2",
            "third": "3",
            "fourth": "4",
            "last": "-1",
        }
        repeat_unit = repeat_unit_dict.get(pattern["type"], pattern["type"])
        interval = pattern["interval"]
        result = {
            "repeat_unit": repeat_unit,
            "repeat_type": repeat_type_dict.get(range["type"], False),
            "repeat_interval": interval,
            "repeat_number": range["numberOfOccurrences"],
            "day": pattern["dayOfMonth"],
            "byday": index_dict.get(pattern["index"], False),
            "repeat_until": range["type"] == "endDate" and range["endDate"],
        }

        month_by_dict = {
            "absoluteMonthly": "date",
            "relativeMonthly": "day",
            "absoluteYearly": "date",
            "relativeYearly": "day",
        }
        month_by = month_by_dict.get(pattern["type"], False)
        if month_by:
            result["month_by"] = month_by

        # daysOfWeek contains the full name of the day, the fields contain the first 3 letters (mon, tue, etc)
        week_days = [x[:3] for x in pattern.get("daysOfWeek", [])]
        # Outlook's "last day of the month" is the last of any weekday
        if (
            pattern["type"] == "relativeMonthly"
            and result["byday"]
            and len(set(week_days)) == 7
        ):
            result["month_by"] = "date"
            result["day"] = int(result["byday"])
            _debug.logic("microsoft.recurrence_any_day_as_date", day=result["day"])
        for week_day in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
            result[week_day] = week_day in week_days
        if week_days:
            result["weekday"] = week_days[0].upper()
        return result

    def is_cancelled(self) -> bool:
        return bool(bool(self.isCancelled) or self.is_removed())

    def is_removed(self) -> bool:
        return bool(
            self.__getattr__("@removed")
            and self.__getattr__("@removed").get("reason") == "deleted"
        )

    def is_recurrence_outlier(self) -> bool:
        return self.type == "exception"

    def cancelled(self):
        return self.filter(lambda e: e.is_cancelled())
