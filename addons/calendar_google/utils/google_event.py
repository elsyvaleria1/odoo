import re

from odoo.tools import email_normalize

from odoo.addons.calendar_sync.provider_events import ProviderEvents


class GoogleEvent(ProviderEvents):
    @property
    def rrule(self):
        if self.recurrence and any("RRULE" in item for item in self.recurrence):
            return next(item for item in self.recurrence if "RRULE" in item)
        return None

    def _meta_odoo_id(self, dbname) -> int | None:
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
        real_owner_id = self.extendedProperties and self.extendedProperties.get(
            "shared", {}
        ).get("%s_owner_id" % env.cr.dbname)
        try:
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
            org_email = email_normalize(self.organizer.get("email"))
            return env["res.users"].search(
                [("email_normalized", "=", org_email)], limit=1
            )
        else:
            return env["res.users"]

    def is_recurrence(self) -> bool:
        return bool(self.recurrence)

    def is_recurrent(self) -> bool:
        return bool(self.recurringEventId or self.is_recurrence())

    def is_cancelled(self) -> bool:
        return self.status == "cancelled"

    def is_recurrence_follower(self) -> bool:
        return bool(not self.originalStartTime or self.originalStartTime == self.start)

    def full_recurring_event_id(self) -> str | None:
        if not self.is_recurrent():
            return None
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
