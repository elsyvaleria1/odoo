from datetime import timedelta

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _calendar_sync_run(self, code: str) -> bool:
        if code == "microsoft" and self._calendar_sync_active("microsoft"):
            self._microsoft_first_synchronization()
        return super()._calendar_sync_run(code)

    def _microsoft_first_synchronization(self) -> None:
        """Outlook is sent the events created since the database first
        synchronized with it, not the history before: the date is kept the
        first time any calendar synchronizes, and an account starts from it."""
        ICP = self.env["ir.config_parameter"].sudo()
        first = ICP.get_param("calendar_microsoft.sync.first_synchronization_date")
        if not first:
            synchronized = (
                self.env["calendar.sync.account"]
                .sudo()
                .search_count(
                    [("provider", "=", "microsoft"), ("sync_token", "!=", False)],
                    limit=1,
                )
            )
            if synchronized:
                return
            # a minute back, so the run's own writes are after it
            first = fields.Datetime.now() - timedelta(minutes=1)
            ICP.set_param("calendar_microsoft.sync.first_synchronization_date", first)
        account = self._calendar_sync_account("microsoft")
        if not account.insert_since:
            account.insert_since = first
