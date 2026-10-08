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
        """The user may come back with another Outlook account: their calendar
        forgets what it held, and keeps or deletes the events they organize."""
        self.check_singleton()
        account = self.user_id._calendar_sync_account("microsoft")._as_engine()
        Link = self.env["calendar.sync.link"]._engine()
        links = Link.search([("account_id", "=", account.id)])
        organized = links.event_id.with_env(self.env).filtered(
            lambda event: event.user_id == self.user_id
        )
        if self.delete_policy in ("delete_microsoft", "delete_both"):
            adapter = account._adapter().with_context(calendar_sync_interactive=True)
            # a series is left to Outlook, where one delete would remove it all
            for link in links.filtered(
                lambda link: (
                    link.remote_id
                    and link.event_id in organized
                    and not link.event_id.recurrence_id
                )
            ):
                account._call(adapter._delete, account, link.remote_id)
        links.unlink()
        if self.delete_policy in ("delete_odoo", "delete_both"):
            organized.with_context(
                dont_notify=True, calendar_sync_applying="microsoft"
            ).unlink()
        self.env["integration.connection"]._find_personal(
            self.env.ref("integration_microsoft.service_microsoft"), self.user_id
        )._forget_oauth_authorization()
        account.write(
            {
                "sync_token": False,
                "last_sync_date": False,
                "insert_since": fields.Datetime.now()
                if self.sync_policy == "new"
                else account.insert_since,
            }
        )
