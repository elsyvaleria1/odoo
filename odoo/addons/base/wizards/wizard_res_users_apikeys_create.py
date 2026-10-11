import datetime
import logging
from typing import Any, Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.service import api_scope

from ..models.res_users import check_identity

_logger = logging.getLogger(__name__)

_debug = DebugLog(__name__)


class WizardResUsersApikeysCreate(models.TransientModel):
    _name = "wizard.res.users.apikeys.create"
    _description = "API Key Description"

    def _selection_duration(self) -> list[tuple[str, str]]:
        durations = [
            ("1", "1 Day"),
            ("7", "1 Week"),
            ("30", "1 Month"),
            ("90", "3 Months"),
            ("180", "6 Months"),
            ("365", "1 Year"),
        ]
        persistent_duration = (
            "0",
            "Persistent Key",
        )
        custom_duration = (
            "-1",
            "Custom Date",
        )
        if self.env.is_system():
            return durations + [persistent_duration, custom_duration]
        max_duration = self.env["res.users.apikeys"]._get_max_duration()
        offered = list(
            filter(lambda duration: int(duration[0]) <= max_duration, durations)
        ) + [custom_duration]
        _debug.logic(
            "apikey_durations_offered",
            uid=self.env.uid,
            max_days=max_duration,
            offered=len(offered),
        )
        return offered

    name = fields.Char(
        string="Description",
        required=True,
    )
    scope_id = fields.Many2one(
        comodel_name="res.users.apikeys.scope",
        string="Door",
        default=lambda self: self.env["res.users.apikeys.scope"]._get_declared_state(
            api_scope.RPC_SCOPE
        )[0],
        required=True,
        help="The one door the key opens: RPC (XML-RPC, JSON-2) or one "
        "integration's. A key opens no other door.",
    )
    duration = fields.Selection(
        selection="_selection_duration",
        default=lambda self: self._selection_duration()[0][0],
        required=True,
    )
    expiration_date = fields.Datetime(
        compute="_compute_expiration_date",
        store=True,
        readonly=False,
    )

    @api.depends("duration")
    def _compute_expiration_date(self) -> None:
        for record in self:
            duration = int(record.duration)
            if duration >= 0:
                record.expiration_date = (
                    fields.Datetime.now() + datetime.timedelta(days=duration)
                    if duration
                    else None
                )

    @api.onchange("expiration_date")
    def _onchange_expiration_date(self) -> dict[str, Any] | None:
        try:
            self.env["res.users.apikeys"]._check_expiration_date(self.expiration_date)
        except UserError as error:
            _debug.logic("apikey_expiration_onchange_warned", uid=self.env.uid)
            warning = {
                "type": "notification",
                "title": self.env._("The API key duration is not correct."),
                "message": error.args[0],
            }
            return {"warning": warning}

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        records = super().create(vals_list)
        _debug.lifecycle("apikey_description_created", count=len(records))
        apikeys = self.env["res.users.apikeys"]
        for record in records:
            apikeys._check_expiration_date(record.expiration_date)
        return records

    @check_identity
    def action_generate_key(self) -> dict[str, Any]:
        self.check_access_generate_key()

        description = self.sudo()
        k = self.env["res.users.apikeys"]._generate(
            description.scope_id.key, description.name, self.expiration_date
        )
        _debug.lifecycle("apikey_wizard_done", uid=self.env.uid, wizard=self.id)
        description.unlink()

        return {
            "type": "ir.actions.act_window",
            "res_model": "res.users.apikeys.show",
            "name": self.env._("API Key Ready"),
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_key": k,
            },
        }

    def check_access_generate_key(self) -> None:
        self.env["res.users.apikeys"]._check_generate_access()
