from odoo import Command, api, fields, models
from odoo.fields import Domain

from odoo.addons.resource.models.utils import filter_domain_leaf


class WizardPlanningSlotPublish(models.TransientModel):
    _name = "wizard.planning.slot.publish"
    _inherit = ["mixin.hr"]
    _description = "Send Planning"

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if "slot_ids" in res and "resource_ids" in fields:
            resources = (
                self.env["planning.slot"]
                .browse(res["slot_ids"][0][2])
                .filtered(lambda slot: slot.resource_type == "human")
                .resource_id
            )
            res["resource_ids"] = [Command.set(resources.sudo().sorted("name").ids)]
        return res

    start_datetime = fields.Datetime(
        string="Period",
        required=True,
    )
    end_datetime = fields.Datetime(
        string="Stop Date",
        required=True,
    )
    include_unassigned = fields.Boolean(
        string="Include Open Shifts",
        default=True,
    )
    note = fields.Text(
        string="Extra Message",
        help="Additional message displayed in the email sent to the people scheduled",
    )
    resource_ids = fields.Many2many(
        comodel_name="resource.resource",
        string="People",
        compute="_compute_slots_data",
        inverse="_inverse_resource_ids",
        compute_sudo=True,
        store=True,
    )
    slot_ids = fields.Many2many(
        comodel_name="planning.slot",
        export_string_translation=False,
        compute="_compute_slots_data",
        store=True,
    )
    resources_no_email = fields.Many2many(
        comodel_name="resource.resource",
        string="People without an email address",
        export_string_translation=False,
        compute="_compute_resources_no_email",
        inverse="_inverse_resources_no_email",
        compute_sudo=True,
    )

    def _get_domain_slot(self):
        self.check_singleton()

        # Our datetime conditions (these will override any from active_domain)
        datetime_domain = [
            ("start_datetime", ">=", self.start_datetime),
            ("end_datetime", "<=", self.end_datetime),
        ]

        active_domain = self.env.context.get("active_domain", [])

        if not active_domain:
            return datetime_domain

        # Remove conditions with 'start_datetime' or 'end_datetime' where the value is not False,
        cleaned_active_domain = filter_domain_leaf(
            active_domain, lambda field: field not in ["start_datetime", "end_datetime"]
        )

        # Combine domains: cleaned active_domain + our datetime
        return Domain.AND([cleaned_active_domain, datetime_domain])

    @api.depends("start_datetime", "end_datetime")
    def _compute_slots_data(self) -> None:
        for wiz in self:
            wiz.slot_ids = (
                self.env["planning.slot"]
                .with_user(self.env.user)
                .search(self._get_domain_slot(), order="employee_id")
            )
            wiz.resource_ids = wiz.slot_ids.filtered(
                lambda s: s.resource_type == "human"
            ).mapped("resource_id")

    def _inverse_resource_ids(self) -> None:
        for wiz in self:
            wiz.slot_ids = (
                self.env["planning.slot"]
                .with_user(self.env.user)
                .search(self._get_domain_slot())
            )

    @api.depends("resource_ids")
    def _compute_resources_no_email(self) -> None:
        for planning in self:
            planning.resources_no_email = planning.resource_ids.filtered(
                lambda resource: not resource._get_planning_email()
            )

    def _inverse_resources_no_email(self) -> None:
        for planning in self:
            planning.resource_ids = planning.resources_no_email + (
                planning.resource_ids.filtered(
                    lambda resource: resource._get_planning_email()
                )
            )

    def get_people_without_email(self) -> dict | None:
        self.check_singleton()
        if not self.resources_no_email or not self.resources_no_email.has_access(
            "write"
        ):
            return None
        context = dict(
            self.env.context,
            force_email=True,
            form_view_ref="planning.resource_resource_view_form_email",
        )
        return {
            "relation": "resource.resource",
            "res_ids": self.resources_no_email.ids,
            "context": context,
        }

    def action_check_emails(self):
        if self.resources_no_email and self.resources_no_email.has_access("write"):
            return {
                "name": self.env._("No Email Address for Some People"),
                "view_mode": "form",
                "res_model": "wizard.planning.slot.publish",
                "views": [
                    (self.env.ref("planning.employee_no_email_list_wizard").id, "form")
                ],
                "type": "ir.actions.act_window",
                "res_id": self.id,
                "target": "new",
            }
        return self.action_send()

    def action_send(self):
        resources = self.resource_ids - self.resources_no_email
        if self.include_unassigned:
            slot_to_send = self.slot_ids.filtered(
                lambda s: not s.resource_id or s.resource_id in resources
            )
        else:
            slot_to_send = self.slot_ids.filtered(lambda s: s.resource_id in resources)
        if not slot_to_send:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "danger",
                    "message": self.env._(
                        "The shifts have already been published, or there are no shifts to publish."
                    ),
                },
            }

        planning = self.env["planning.planning"]._get_or_create_preview_planning(
            self.start_datetime, self.end_datetime, self.include_unassigned
        )
        planning.is_planning_preview = False
        planning.include_unassigned = self.include_unassigned

        slot_resources = slot_to_send.mapped("resource_id")
        open_slots = slot_to_send.filtered(
            lambda s: not s.resource_id and not s.is_past
        )
        resources_to_send = self.env["resource.resource"]
        for resource in resources:
            if resource in slot_resources:
                resources_to_send |= resource
            else:
                for slot in open_slots:
                    if (
                        not resource.role_ids
                        or not slot.role_id
                        or slot.role_id in resource.role_ids
                    ):
                        resources_to_send |= resource
                        break
        res = planning._send_planning(
            slots=slot_to_send, message=self.note, resources=resources_to_send
        )
        if res:
            if self.resources_no_email:
                message = self.env._(
                    "Shifts published — people without an email address were skipped"
                )
                notification_type = "info"
            else:
                message = self.env._("Schedule sent to the people scheduled")
                notification_type = "success"
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": notification_type,
                    "message": message,
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }
        return None
