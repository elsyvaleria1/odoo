from odoo import fields, models


class WizardResUsersResetMicrosoftCalendar(models.TransientModel):
    _name = "wizard.res.users.reset.microsoft.calendar"
    _description = "Microsoft Calendar Account Reset"

    user_id = fields.Many2one(
        comodel_name="res.users",
        required=True,
    )
    delete_policy = fields.Selection(
        selection=[
            ("dont_delete", "Leave them untouched"),
            ("delete_microsoft", "Delete from the current Microsoft Calendar account"),
            ("delete_odoo", "Delete from Odoo"),
            ("delete_both", "Delete from both"),
        ],
        string="User's Existing Events",
        default="dont_delete",
        required=True,
        help="This will only affect events for which the user is the owner",
    )
    sync_policy = fields.Selection(
        selection=[
            ("new", "Synchronize only new events"),
            ("all", "Synchronize all existing events"),
        ],
        string="Next Synchronization",
        default="new",
        required=True,
    )

    def reset_account(self) -> None:
        # We don't update recurring events to prevent spam
        events = self.env["calendar.event"].search(
            [("user_id", "=", self.user_id.id), ("ms_universal_event_id", "!=", False)]
        )

        if self.delete_policy in ("delete_microsoft", "delete_both"):
            for event in events.filtered(lambda event: not event.recurrence_id):
                event._microsoft_delete(
                    event._get_organizer(), event.microsoft_id, timeout=3
                )

        events = events.with_context(dont_notify=True, microsoft_calendar_syncing=True)
        if self.delete_policy != "dont_delete" or self.sync_policy == "all":
            # Both ids go: `_filtered_synced` reads the universal one, so a record
            # keeping it was still patched or deleted, at `/events/False`.
            events.write({"microsoft_id": False, "ms_universal_event_id": False})
        if self.delete_policy in ("delete_odoo", "delete_both"):
            events.unlink()
        else:
            events.need_sync_m = self.sync_policy == "all"

        # We commit to make sure the _microsoft_delete are called when we still have a token on the user.
        self.env["ir.cron"]._commit_progress()
        self.user_id._set_microsoft_auth_tokens(False, False, 0)
        self.user_id.res_users_settings_id.write(
            {"microsoft_calendar_sync_token": False, "microsoft_last_sync_date": False}
        )
