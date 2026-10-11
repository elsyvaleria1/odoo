import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class MarketingActivity(models.Model):
    _inherit = "marketing.activity"

    activity_type = fields.Selection(
        selection_add=[("sms", "SMS")],
        ondelete={"sms": "cascade"},
    )
    mass_mailing_id_mailing_type = fields.Selection(selection_add=[("sms", "SMS")])
    trigger_type = fields.Selection(
        selection_add=[
            ("sms_click", "SMS: clicked"),
            ("sms_not_click", "SMS: not clicked"),
            ("sms_bounce", "SMS: bounced"),
        ],
        ondelete={
            "sms_click": "cascade",
            "sms_not_click": "cascade",
            "sms_bounce": "cascade",
        },
    )
    trigger_category = fields.Selection(
        selection_add=[("sms", "SMS")],
        compute="_compute_trigger_category",
    )

    @api.depends("activity_type")
    def _compute_mass_mailing_id_mailing_type(self) -> None:
        for activity in self:
            if activity.activity_type == "sms":
                activity.mass_mailing_id_mailing_type = "sms"
        super()._compute_mass_mailing_id_mailing_type()

    @api.depends("trigger_type")
    def _compute_trigger_category(self) -> None:
        non_sms_trigger_category = self.env["marketing.activity"]
        for activity in self:
            if activity.trigger_type in ["sms_click", "sms_not_click", "sms_bounce"]:
                activity.trigger_category = "sms"
            else:
                non_sms_trigger_category |= activity

        super(MarketingActivity, non_sms_trigger_category)._compute_trigger_category()

    def _get_activity_executors(self):
        return super()._get_activity_executors() | {"sms": self._execute_sms}

    def _execute_sms(self, traces) -> bool:
        if not self.env.is_superuser() and not self.env.user.has_group(
            "marketing_automation.group_marketing_automation_user"
        ):
            raise AccessError(
                self.env._(
                    "To use this feature you should be an administrator or belong to the marketing automation group."
                )
            )

        res_ids = list(dict.fromkeys(traces.mapped("res_id")))
        mailing = self.mass_mailing_id.sudo().with_context(
            default_marketing_activity_id=self.ids[0],
            marketing_trace_ids=traces.ids,
        )
        try:
            mailing.action_send_sms(res_ids)
        except Exception as e:
            _logger.warning(
                "Marketing Automation: activity <%s> encountered mass mailing issue %s",
                self.id,
                e,
                exc_info=True,
            )
            traces._settle_line(
                "error",
                message=self.env._("Exception in SMS Marketing: %s", e),
                advance=False,
            )
            return True

        failed_stats = (
            self.env["mailing.trace"]
            .sudo()
            .search(
                [
                    ("marketing_trace_id", "in", traces.ids),
                    ("trace_status", "in", ["error", "cancel"]),
                ]
            )
        )
        cancel_doc_ids = {
            stat.res_id for stat in failed_stats if stat.trace_status == "cancel"
        }
        error_doc_ids = {
            stat.res_id for stat in failed_stats if stat.trace_status == "error"
        }
        canceled = traces.filtered(lambda trace: trace.res_id in cancel_doc_ids)
        failed = traces.filtered(lambda trace: trace.res_id in error_doc_ids)
        canceled._settle_line(
            "canceled", message=self.env._("SMS cancelled"), advance=False
        )
        failed._settle_line("error", message=self.env._("SMS failed"), advance=False)
        (traces - canceled - failed)._settle_line("processed", advance=False)
        return True
