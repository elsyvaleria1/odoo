import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

DEFAULT_REVEAL_VIEW_WEEKS_VALID = 5
_debug = DebugLog(__name__)


class CrmRevealView(models.Model):
    _name = "crm.reveal.view"
    _description = "CRM Reveal View"
    _rec_name = "reveal_ip"
    _order = "id desc"
    _access_anchors = frozendict(
        {
            "owner": models.Anchor("reveal_rule_id.user_id", shared=True),
        }
    )

    reveal_ip = fields.Char(string="IP Address")
    reveal_rule_id = fields.Many2one(
        comodel_name="crm.reveal.rule",
        string="Lead Generation Rule",
        index="btree_not_null",
    )
    reveal_state = fields.Selection(
        selection=[("to_process", "To Process"), ("not_found", "Not Found")],
        string="State",
        default="to_process",
        index=True,
    )
    create_date = fields.Datetime(index=True)

    _ip_rule_id = models.UniqueIndex(
        "(reveal_rule_id, reveal_ip) "
        "WHERE reveal_rule_id IS NOT NULL AND reveal_ip IS NOT NULL"
    )
    _state_create_date = models.Index("(reveal_state,create_date)")

    @api.model
    def _clean_reveal_views(self) -> None:
        weeks_valid = self.env.registry.settings.get(
            self.env, "reveal.view_weeks_valid", DEFAULT_REVEAL_VIEW_WEEKS_VALID
        )
        try:
            weeks_valid = int(weeks_valid)
        except ValueError:
            _debug.logic("reveal_param_rejected", param="view_weeks_valid")
            weeks_valid = DEFAULT_REVEAL_VIEW_WEEKS_VALID
        domain = []
        domain.append(("reveal_state", "=", "not_found"))
        domain.append(
            (
                "create_date",
                "<",
                fields.Datetime.to_string(
                    datetime.date.today() - relativedelta(weeks=weeks_valid)
                ),
            )
        )
        self.search(domain).unlink()

    def _create_reveal_view(self, rules, ip_address, rules_excluded) -> list:
        self.env.cr.execute(
            SQL(
                """
                INSERT INTO crm_reveal_view (reveal_ip, reveal_rule_id, reveal_state, create_date)
                VALUES %s
                ON CONFLICT DO NOTHING
                """,
                SQL(", ").join(
                    SQL(
                        "(%s, %s, 'to_process', now() at time zone 'UTC')",
                        ip_address,
                        rule["id"],
                    )
                    for rule in rules
                ),
            )
        )
        return [*rules_excluded, *(str(rule["id"]) for rule in rules)]
