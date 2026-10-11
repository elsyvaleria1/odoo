from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SpreadsheetCellThread(models.Model):
    _name = "spreadsheet.cell.thread"

    _description = "Spreadsheet discussion thread"

    _inherit = ["mixin.mail.thread"]

    display_name = fields.Char(compute_sudo=True)

    def _compute_display_name(self):
        for record in self:
            record.display_name = record._get_spreadsheet_record().display_name

    @api.model_create_multi
    def create(self, vals_list):
        return super(
            SpreadsheetCellThread, self.with_context(mail_create_nolog=True)
        ).create(vals_list)

    def _notify_thread_by_email(
        self, message, recipients_data, *, msg_vals=False, **kwargs
    ):
        msg_vals = msg_vals or {}
        msg_vals["email_layout_xmlid"] = "spreadsheet_edition.mail_notification_layout"
        return super()._notify_thread_by_email(
            message, recipients_data, msg_vals=msg_vals, **kwargs
        )

    def _message_compute_subject(self):
        self.check_singleton()
        return self.env._("New Mention in %s") % self.display_name

    @api.readonly
    def get_spreadsheet_access_action(self):
        related_record = self._get_spreadsheet_record()
        can_read = bool(related_record and related_record.has_access("read"))
        _debug.logic(
            "spreadsheet_thread_access_action",
            records=self,
            spreadsheet=related_record or None,
            granted=can_read,
        )
        if can_read:
            action = related_record.action_view_spreadsheet()
            action["params"] = action.get("params", {})
            action["params"]["thread_id"] = self.id
            return action
        else:
            return {
                "type": "ir.actions.client",
                "tag": "home",
            }

    def _get_access_action(self, access_uid=None, force_website=False):
        self.check_singleton()

        related_record = self._get_spreadsheet_record()
        if related_record:
            url = "/web/?action=%s&spreadsheet_id=%s&thread_id=%s" % (
                related_record.action_view_spreadsheet().get("tag"),
                related_record.id,
                self.id,
            )

            return {
                "type": "ir.actions.act_url",
                "url": url,
                "target_type": "public",
            }

        return super()._get_access_action(
            access_uid=access_uid, force_website=force_website
        )

    def _get_spreadsheet_record(self):
        return False
