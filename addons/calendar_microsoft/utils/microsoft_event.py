from odoo.libs.debug_log import DebugLog
from odoo.tools import email_normalize

from odoo.addons.calendar_sync.provider_events import ProviderEvents

_debug = DebugLog(__name__)


class MicrosoftEvent(ProviderEvents):

    @property
    def uids(self):
        return tuple(e.iCalUId for e in self)

    def owner_id(self, env):
        if self.isOrganizer:
            return env.user.id

        if not self.organizer:
            return False

        organizer_email = self.organizer.get("emailAddress") and email_normalize(
            self.organizer.get("emailAddress").get("address")
        )
        if organizer_email:
            user = env["res.users"].search([("email", "=", organizer_email)], limit=1)
            return user.id if user else False
        return False

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

        week_days = [x[:3] for x in pattern.get("daysOfWeek", [])]
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
