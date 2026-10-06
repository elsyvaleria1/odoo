from typing import Any

from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HomeTile(models.AbstractModel):
    _inherit = "home.tile"

    _ACTIVITY_GROUPS_SHOWN = 6
    _INBOX_MESSAGES_SHOWN = 5

    @api.model
    def _get_starter_tiles(self) -> list[dict[str, str]]:
        return [
            {"id": "activities_1", "type": "activities", "size": "1x1"},
            *super()._get_starter_tiles(),
        ]

    @api.model
    def _get_tile_types(self) -> dict[str, dict[str, Any]]:
        return {
            **super()._get_tile_types(),
            "activities": {
                "name": self.env._("Activities"),
                "sizes": ["1x1", "2x1"],
                "model": "mail.activity",
            },
            "inbox": {
                "name": self.env._("Inbox"),
                "sizes": ["2x1"],
                "model": "mail.message",
            },
        }

    @api.model
    def _get_tile_activities_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        groups = [
            group
            for group in self.env.user._get_activity_groups()
            if group["type"] == "activity"
        ]
        totals = {
            bucket: sum(group.get(f"{bucket}_count", 0) for group in groups)
            for bucket in ("overdue", "today", "planned")
        }
        busiest = sorted(groups, key=lambda group: -group.get("due_count", 0))
        _debug.logic("activities_tile", groups=len(groups), **totals)
        return {
            **totals,
            "groups": [
                {
                    "model": group["model"],
                    "subkey": group["subkey"],
                    "domain": group["domain"],
                    "name": group["name"],
                    "icon": group["icon"],
                    # what the activity systray opens a group with: the tile
                    # opens it through the same activityGroupOpener
                    "activity_ids": group.get("activity_ids", []),
                    "view_type": group.get("view_type"),
                    "is_todo": group.get("is_todo", False),
                    "overdue": group.get("overdue_count", 0),
                    "today": group.get("today_count", 0),
                    "planned": group.get("planned_count", 0),
                }
                for group in busiest[: self._ACTIVITY_GROUPS_SHOWN]
            ],
        }

    @api.model
    def _get_tile_inbox_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        messages = self.env["mail.message"].search(
            [("needaction", "=", True), ("model", "!=", "discuss.channel")],
            limit=self._INBOX_MESSAGES_SHOWN,
            order="id desc",
        )
        count = self.env.user.partner_id._get_needaction_count()
        # a notified user reads the message, not always the record it is on;
        # the tile opens only what they can read, else the inbox
        readable: set[tuple[str, int]] = set()
        for model, grouped in messages.filtered("res_id").grouped("model").items():
            if model in self.env:
                records = self.env[model].browse(grouped.mapped("res_id")).exists()
                readable.update(
                    (model, rid) for rid in records._filtered_access("read").ids
                )
        _debug.logic("inbox_tile", count=count, shown=len(messages))

        def row(message: Any) -> dict[str, Any]:
            on_record = (message.model, message.res_id) in readable
            return {
                "id": message.id,
                "author": message.author_id.display_name or message.email_from or "",
                "record_name": message.record_name or "",
                "model": message.model if on_record else False,
                "res_id": message.res_id if on_record else False,
                "date": message.date,
                "preview": message.preview or "",
            }

        return {"count": count, "messages": [row(message) for message in messages]}
