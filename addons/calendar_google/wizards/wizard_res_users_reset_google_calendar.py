from odoo import fields, models


class WizardResUsersResetGoogleCalendar(models.TransientModel):
    _name = "wizard.res.users.reset.google.calendar"
    _description = "Google Calendar Account Reset"

    user_id = fields.Many2one(
        comodel_name="res.users",
        required=True,
    )
    delete_policy = fields.Selection(
        selection=[
            ("dont_delete", "Leave them untouched"),
            ("delete_google", "Delete from the current Google Calendar account"),
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
        account = self.user_id._calendar_sync_account("google")._as_engine()
        events = self.env["calendar.event"].search(
            [("user_id", "=", self.user_id.id), ("google_id", "!=", False)]
        )
        recurrences = self.env["calendar.recurrence"].search(
            [("base_event_id", "in", events.ids), ("google_id", "!=", False)]
        )
        Link = self.env["calendar.sync.link"]
        links = Link._of(events, "google") | Link._of(recurrences, "google")

        # deleted now, while the account the user leaves can still be reached
        if self.delete_policy in ("delete_google", "delete_both"):
            adapter = self.env["calendar.sync.adapter.google"]
            for google_id in set(Link._of(events, "google").mapped("remote_id")):
                adapter._delete(account, google_id)

        # the user's events forget their Google ids, or go with them
        if self.delete_policy in ("delete_odoo", "delete_both", "delete_google"):
            links.unlink()
            if self.delete_policy != "delete_google":
                events.unlink()
        else:
            # kept linked: sent again with every event, or left as they are
            links.pending = self.sync_policy == "all"

        account.write(
            {
                "sync_token": False,
                # "new": what exists now is not sent; "all": every event is
                "insert_since": (
                    fields.Datetime.now() if self.sync_policy == "new" else False
                ),
            }
        )
        self.env["integration.connection"]._find_personal(
            self.env.ref("integration_google.service_google"), self.user_id
        )._forget_oauth_authorization()
