import operator
from typing import Any

from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardProjectProjectShare(models.TransientModel):
    _name = "wizard.project.project.share"
    _inherit = ["wizard.mail.message.send.portal.link"]
    _description = "Project Sharing"

    @api.model
    def default_get(self, fields: list[str]) -> dict[str, Any]:
        active_model = self.env.context.get("active_model", "")
        active_id = self.env.context.get("active_id", False)
        if active_model == "project.collaborator":
            active_model = "project.project"
            active_id = self.env.context.get("default_project_id", False)
        default_fields = fields
        if "collaborator_ids" in fields:
            default_fields = list(dict.fromkeys([*fields, "res_model", "res_id"]))
        result = super(
            WizardProjectProjectShare,
            self.with_context(active_model=active_model, active_id=active_id),
        ).default_get(default_fields)
        if (
            "collaborator_ids" in fields
            and "collaborator_ids" not in result
            and result.get("res_model") == "project.project"
            and result.get("res_id")
        ):
            project = self.env["project.project"].browse(result["res_id"]).exists()
            collaborator_vals_list = [
                {
                    "partner_id": collaborator.partner_id.id,
                    "partner_name": collaborator.partner_id.display_name,
                    "access_mode": collaborator.access_mode,
                }
                for collaborator in self._live_partner_collaborators(project)
            ]
            _debug.logic(
                "collaborators_prefilled",
                project=project.id,
                rows=len(collaborator_vals_list),
            )
            if collaborator_vals_list:
                collaborator_vals_list.sort(key=operator.itemgetter("partner_name"))
                result["collaborator_ids"] = [
                    Command.create(
                        {
                            "partner_id": collaborator["partner_id"],
                            "access_mode": collaborator["access_mode"],
                            "send_invitation": False,
                        }
                    )
                    for collaborator in collaborator_vals_list
                ]
        return {name: value for name, value in result.items() if name in fields}

    @api.model
    def _selection_target_model(self) -> list[tuple[str, str]]:
        project_model = self.env["ir.model"]._get("project.project")
        return [(project_model.model, project_model.name)]

    share_link = fields.Char(
        string="Public Link",
        help="Anyone with this link can view the project and its tasks, without "
        "commenting, for 30 days.",
    )
    collaborator_ids = fields.One2many(
        comodel_name="wizard.project.project.share.collaborator",
        inverse_name="parent_wizard_id",
        string="Collaborators",
    )
    existing_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        export_string_translation=False,
        compute="_compute_existing_partner_ids",
    )

    @api.depends("res_model", "res_id")
    def _compute_resource_ref(self) -> None:
        for wizard in self:
            if wizard.res_model and wizard.res_model == "project.project":
                wizard.resource_ref = "%s,%s" % (
                    wizard.res_model,
                    wizard.res_id or 0,
                )
            else:
                wizard.resource_ref = None

    @api.depends("collaborator_ids")
    def _compute_existing_partner_ids(self) -> None:
        for wizard in self:
            wizard.existing_partner_ids = wizard.collaborator_ids.partner_id

    @api.model
    def _live_partner_collaborators(self, project: models.Model) -> models.Model:
        now = fields.Datetime.now()
        return project.collaborator_ids.filtered(
            lambda c: c.partner_id and (not c.date_to or c.date_to > now)
        )

    @_debug.perf.timed
    def _sync_collaborators(self) -> None:
        for wizard in self:
            project = wizard.resource_ref
            existing = {
                c.partner_id: c for c in project.collaborator_ids if c.partner_id
            }
            live = self._live_partner_collaborators(project)
            requested = {c.partner_id: c.access_mode for c in wizard.collaborator_ids}
            commands = [
                Command.delete(collaborator.id)
                for collaborator in live
                if collaborator.partner_id not in requested
            ]
            for partner, access_mode in requested.items():
                collaborator = existing.get(partner)
                if not collaborator:
                    continue
                vals = {}
                if collaborator.access_mode != access_mode:
                    vals["access_mode"] = access_mode
                if collaborator not in live:
                    vals["date_to"] = False
                if vals:
                    commands.append(Command.update(collaborator.id, vals))
            new_partners = project._get_new_collaborators(
                self.env["res.partner"].union(*requested)
            )
            commands.extend(
                Command.create(
                    {"partner_id": partner.id, "access_mode": requested[partner]}
                )
                for partner in new_partners
            )
            _debug.pipeline(
                "collaborators_synced",
                project=project.id,
                added=new_partners,
                revived=[
                    partner.id
                    for partner, collaborator in existing.items()
                    if partner in requested and collaborator not in live
                ],
                commands=len(commands),
            )
            if commands:
                project.write({"collaborator_ids": commands})

    def action_share_record(self) -> dict[str, Any] | None:
        self.check_singleton()
        on_invite = self.env["res.users"]._get_signup_invitation_scope() == "b2b"
        new_portal_user = (
            self.collaborator_ids.filtered(
                lambda c: c.send_invitation and not c.partner_id.user_ids
            )
            and on_invite
        )
        _debug.logic(
            "share_record",
            wizard=self,
            b2b=on_invite,
            new_portal_user=bool(new_portal_user),
        )
        if not new_portal_user:
            return self.action_send_mail()
        return {
            "name": self.env._("Confirmation"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "views": [
                (
                    self.env.ref("project.project_share_wizard_confirm_form").id,
                    "form",
                )
            ],
            "res_model": "wizard.project.project.share",
            "res_id": self.id,
            "target": "new",
            "context": self.env.context,
        }

    @_debug.perf.timed
    def action_send_mail(self) -> dict[str, Any]:
        _debug.pipeline("send_mail_sync_requested", wizard=self)
        self._sync_collaborators()
        result = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Project shared with your collaborators."),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
        new_collaborators = self.collaborator_ids.filtered("send_invitation").partner_id
        portal_partners = new_collaborators.filtered("user_ids")
        _debug.pipeline(
            "share_links_sending",
            wizard=self,
            public_link=portal_partners,
            signup_link=new_collaborators - portal_partners,
        )
        invited = self._send_public_link(portal_partners) | self._send_signup_link(
            partners=new_collaborators.with_context({"signup_valid": True})
            - portal_partners
        )
        if invited:
            self._log_share_invitations(invited, record=self._get_shared_record())
        return result
