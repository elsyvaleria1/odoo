import base64

from werkzeug.exceptions import Forbidden

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused

_debug = DebugLog(__name__)


class SpreadsheetDashboardShare(models.Model):
    _name = "spreadsheet.dashboard.share"
    _inherit = ["mixin.spreadsheet"]
    _description = "Copy of a shared dashboard"

    dashboard_id = fields.Many2one(
        comodel_name="spreadsheet.dashboard",
        required=True,
        ondelete="cascade",
    )
    excel_export = fields.Binary()
    access_token = fields.Char(
        compute="_compute_access_token",
        help="The token of the share's link; the link is an access.link row "
        "holding its hash.",
    )
    full_url = fields.Char(
        string="URL",
        compute="_compute_full_url",
    )
    name = fields.Char(related="dashboard_id.name")

    @api.model_create_multi
    def create(self, vals_list):
        shares = super().create(vals_list)
        for share in shares:
            # a copy shared by hand: its link lives as a manual share's does
            # (decision B1)
            self.env["access.link"]._issue(share, role="view", cause="share")
        return shares

    def _compute_access_token(self) -> None:
        links = (
            self.env["access.link"]
            ._record_links(
                self.filtered("id"),
                Domain("cause", "in", ("share", "migration"))
                & Domain("audience", "=", "anyone"),
            )
            .sorted("id", reverse=True)
        )
        shown = links._tokens()
        tokens = {}
        for link in links:
            if link.res_id not in tokens and link.id in shown:
                tokens[link.res_id] = shown[link.id]
        for share in self:
            share.access_token = tokens.get(share.id, False)

    @api.depends("access_token")
    def _compute_full_url(self) -> None:
        for share in self:
            share.full_url = "%s/dashboard/share/%s/%s" % (
                share.get_base_url(),
                share.id,
                share.access_token,
            )

    @api.model
    def action_get_share_url(self, vals):
        if "excel_files" in vals:
            excel_zip = self._zip_xslx_files(vals["excel_files"])
            del vals["excel_files"]
            vals["excel_export"] = base64.b64encode(excel_zip)
        share = self.create(vals)
        _debug.lifecycle(
            "dashboard_share_created",
            share=share,
            dashboard_id=vals.get("dashboard_id"),
            with_excel="excel_export" in vals,
        )
        return share.full_url

    def _is_access_token_matching(self, access_token) -> bool:
        self.check_singleton()
        try:
            self.env["access.link"]._resolve(
                access_token, model=self._name, res_id=self.id, action=None
            )
        except LinkRefused, LinkLoginRequired:
            return False
        return True

    def _check_dashboard_access(self, access_token) -> None:
        self.check_singleton()
        token_access = self._is_access_token_matching(access_token)
        dashboard = self.dashboard_id.with_user(self.create_uid)
        user_access = dashboard.has_access("read")
        if not (token_access and user_access):
            _debug.logic(
                "dashboard_share_access_denied",
                share=self,
                token_valid=token_access,
                creator_can_read=user_access,
            )
            raise Forbidden(self.env._("You don't have access to this dashboard. "))
