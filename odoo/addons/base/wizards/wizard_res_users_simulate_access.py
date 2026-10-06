from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval

from odoo.addons.base.models.ir_access_log import kept_on_uninstall

SIMULATE_LOG_EVENTS = [("simulated", "Someone's reach simulated")]


class IrAccessLog(models.Model):
    _inherit = "ir.access.log"

    event = fields.Selection(
        selection_add=SIMULATE_LOG_EVENTS,
        ondelete=kept_on_uninstall(SIMULATE_LOG_EVENTS),
    )


class WizardResUsersSimulateAccess(models.TransientModel):
    _name = "wizard.res.users.simulate.access"
    _description = "Simulate Someone's Reach"

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Person",
        required=True,
        help="Whose reach is simulated: their groups, grants and companies, "
        "without logging in as them.",
    )
    model_name = fields.Selection(
        selection="_selection_models",
        string="Model",
        required=True,
    )
    domain = fields.Char(
        default="[]",
        help="Only the records of this domain.",
    )
    reached_count = fields.Integer(
        string="They Reach",
        readonly=True,
    )
    shared_count = fields.Integer(
        string="You Both Reach",
        readonly=True,
    )
    hidden_count = fields.Integer(
        string="Only They Reach",
        readonly=True,
        help="Records the person reads that you do not: counted, never shown.",
    )
    extra_count = fields.Integer(
        string="Only You Reach",
        readonly=True,
    )
    shared_ids = fields.Json(readonly=True)
    extra_ids = fields.Json(readonly=True)

    @api.model
    def _selection_models(self) -> list[tuple[str, str]]:
        registry = self.env.registry
        return sorted(
            (name, registry[name]._description or name)
            for name in registry.models
            if not registry[name]._abstract and not registry[name]._transient
        )

    def action_simulate(self) -> dict[str, Any]:
        self.check_singleton()
        if self.user_id == self.env.user:
            raise UserError(self.env._("Simulate someone else: your reach is yours."))
        domain = Domain(safe_eval(self.domain or "[]"))
        principal = self.user_id
        theirs = set(
            self.env(
                user=principal,
                context={"allowed_company_ids": principal.company_ids.ids},
            )[self.model_name]
            .search(domain)
            .ids
        )
        mine = set(self.env[self.model_name].search(domain).ids)
        shared = sorted(theirs & mine)
        extra = sorted(mine - theirs)
        self.write(
            {
                "reached_count": len(theirs),
                "shared_count": len(shared),
                "hidden_count": len(theirs - mine),
                "extra_count": len(extra),
                "shared_ids": shared,
                "extra_ids": extra,
            }
        )
        self.env["ir.access.log"]._record(
            [
                {
                    "event": "simulated",
                    "subject_user_id": principal.id,
                    "model_name": self.model_name,
                    "operation": "read",
                    "count": len(theirs),
                    "reason": self.domain or False,
                }
            ]
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_open_shared(self) -> dict[str, Any]:
        return self._open(
            self.shared_ids, self.env._("Reached by %s and you", self.user_id.name)
        )

    def action_open_extra(self) -> dict[str, Any]:
        return self._open(
            self.extra_ids, self.env._("Reached by you, not by %s", self.user_id.name)
        )

    def _open(self, ids: list[int] | None, title: str) -> dict[str, Any]:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": self.model_name,
            "view_mode": "list,form",
            "domain": [("id", "in", ids or [])],
            "context": {"create": False},
        }
