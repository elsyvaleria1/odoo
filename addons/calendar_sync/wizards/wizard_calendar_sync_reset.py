from odoo import api, fields, models


class WizardCalendarSyncReset(models.TransientModel):
    """Start a user's synchronization with a provider over: the user may come
    back with another account, so their calendar's links are forgotten, and
    the events they organize are kept or deleted."""

    _name = "wizard.calendar.sync.reset"
    _description = "Calendar Synchronization Reset"

    provider = fields.Selection(
        selection="_selection_provider",
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        required=True,
    )
    delete_policy = fields.Selection(
        selection=[
            ("dont_delete", "Leave them untouched"),
            ("delete_remote", "Delete from the account's calendar"),
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

    @api.model
    def _selection_provider(self) -> list[tuple[str, str]]:
        return [
            (code, provider.label)
            for code, provider in self.env["calendar.sync.account"]
            ._calendar_sync_providers()
            .items()
        ]

    def reset_account(self) -> None:
        self.check_singleton()
        code = self.provider
        account = self.user_id._calendar_sync_account(code)._as_engine()
        Link = self.env["calendar.sync.link"]._engine()
        links = Link.search([("account_id", "=", account.id)])
        organized = links.filtered(
            lambda link: (
                (link.event_id.user_id or link.recurrence_id.base_event_id.user_id)
                == self.user_id
            )
        )
        if self.delete_policy in ("delete_remote", "delete_both"):
            # deleted now, while the account the user leaves can be reached;
            # an event of a series goes with its series
            adapter = account._adapter().with_context(calendar_sync_interactive=True)
            for link in organized.filtered(
                lambda link: (
                    link.remote_id
                    and not (
                        link.event_id.recurrence_id and link.event_id.follow_recurrence
                    )
                )
            ):
                account._call(adapter._delete, account, link.remote_id)
        events = (
            organized.event_id | organized.recurrence_id.calendar_event_ids
        ).with_env(self.env)
        links.unlink()
        if self.delete_policy in ("delete_odoo", "delete_both"):
            events.with_context(dont_notify=True, calendar_sync_applying=code).unlink()
        self.env["integration.connection"]._find_personal(
            self.env.ref(account._provider(code).service), self.user_id
        )._forget_oauth_authorization()
        account.write(
            {
                "sync_token": False,
                "last_sync_date": False,
                # "new": what exists now is not sent; "all": every event is
                "insert_since": fields.Datetime.now()
                if self.sync_policy == "new"
                else False,
            }
        )
