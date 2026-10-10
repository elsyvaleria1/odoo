from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class CustomerStatementCustomHandler(models.AbstractModel):
    _name = "account.customer.statement.report.handler"
    _inherit = "account.partner.ledger.report.handler"
    _description = "Customer Statement Custom Handler"

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(report, options, previous_options)
        self._init_statement_display_options(options, "action_send_statements", 90)
        options["custom_display_config"]["css_custom_class"] += " customer_statement"

    @_debug.perf.timed
    def action_send_statements(self, options) -> dict:
        _debug.lifecycle("action_send_statements", records=self)
        partners = self.env["res.partner"].browse(options.get("partner_ids", []))
        return self._get_statement_send_action(
            options,
            self.env._("Send %s Statement", partners.name)
            if len(partners) == 1
            else self.env._("Send Partner Ledgers"),
            "account.email_template_customer_statement",
        )
