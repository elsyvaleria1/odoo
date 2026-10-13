from collections import defaultdict

from odoo import fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)

STATUS_SELECTION = [
    ("todo", "To Review"),
    ("reviewed", "Reviewed"),
    ("supervised", "Supervised"),
    ("anomaly", "Anomaly"),
]
STATUS_URGENCY = ("anomaly", "todo", "reviewed", "supervised", False)


class AccountAuditAccountStatus(models.Model):
    _name = "account.audit.account.status"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("audit_id.company_ids", shared=False),
        }
    )
    _description = "Account Audit Account Status"

    audit_id = fields.Many2one(
        comodel_name="account.return",
        index="btree",
        required=True,
        ondelete="cascade",
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        index="btree",
        required=True,
        ondelete="cascade",
    )
    status = fields.Selection(selection=STATUS_SELECTION)

    _audit_id_account_id_uniq = models.Constraint(
        "UNIQUE(audit_id, account_id)",
        "An account holds one review status per audit.",
    )

    def _collapse_to_most_urgent(self, key) -> None:
        kept_by_status = defaultdict(self.browse)
        collapsed = self.browse()
        for rows in self.grouped(key).values():
            if len(rows) < 2:
                continue
            kept = rows.sorted("id")[:1]
            kept_by_status[min(rows.mapped("status"), key=STATUS_URGENCY.index)] |= kept
            collapsed |= rows - kept
        _debug.pipeline(
            "audit_account_statuses_collapsed",
            kept=sum(kept_by_status.values(), self.browse()),
            removed=collapsed,
        )
        collapsed.unlink()
        for status, kept in kept_by_status.items():
            kept.status = status
