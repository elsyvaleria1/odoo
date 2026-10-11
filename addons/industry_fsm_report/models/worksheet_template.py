from odoo import api, models

from odoo.addons.worksheet.models.worksheet_template import WorksheetModelHooks


class WorksheetTemplate(models.Model):
    _inherit = "worksheet.template"

    def action_analysis_report(self):
        res = super().action_analysis_report()
        res["context"] = dict(
            self.env["ir.actions.actions"]._eval_action_context(
                res.get("context", "{}")
            ),
            fsm_mode=True,
        )
        return res

    def action_archive(self):
        res = super().action_archive()
        projects = self.env["project.project"].search(
            [("worksheet_template_id", "in", self.ids)]
        )
        projects.worksheet_template_id = False
        return res

    def _create_worksheet_model(self) -> None:
        super()._create_worksheet_model()
        if self.res_model == "project.task":
            self._create_project_task_worksheet_field()

    def _create_project_task_worksheet_field(self) -> None:
        self.check_singleton()
        model = self.sudo().model_id
        name = f"{model.model}_ids"
        if name in self.env["project.task"]._fields:
            return
        field = (
            self.env["ir.model.fields"]
            .sudo()
            .create(
                {
                    "name": name,
                    "model_id": self.env["ir.model"]._get_id("project.task"),
                    "field_description": self.env._(
                        "Worksheet: %(template)s", template=self.name
                    ),
                    "ttype": "one2many",
                    "relation": model.model,
                    "relation_field": "x_project_task_id",
                    "copied": False,
                }
            )
        )
        self.env["ir.model.data"].sudo().create(
            {
                "name": f"{model.model}_project_task_field",
                "module": "industry_fsm_report",
                "model": "ir.model.fields",
                "res_id": field.id,
                "noupdate": True,
            }
        )

    @api.model
    def _get_models_to_check_dict(self):
        res = super()._get_models_to_check_dict()
        res["project.task"] = [("project.task", "Task"), ("project.project", "Project")]
        return res

    @api.model
    def _get_worksheet_model_hooks(self):
        return super()._get_worksheet_model_hooks() | {
            "project.task": WorksheetModelHooks(
                module="industry_fsm_report",
                user_group="project.group_project_user",
                manager_group="project.group_project_manager",
                access_all_groups=(
                    "project.group_project_manager",
                    "industry_fsm.group_fsm_user",
                ),
                additional_access_vals_list=self._get_project_task_additional_access_vals_list,
            ),
        }

    def _get_project_task_additional_access_vals_list(self, name, model_id) -> list:
        res_model = self.res_model.replace(".", "_")
        return [
            {
                "name": f"{name}_user",
                "model_id": model_id,
                "group_id": self.env.ref("project.group_project_user").id,
                "kind": "permission",
                "operation": "crud",
                "domain": f"[('x_{res_model}_id.user_ids', 'in', user.id)]",
            },
        ]

    def _get_template_action_context(self):
        context = super()._get_template_action_context()
        if self.res_model == "project.task":
            context.update(
                {
                    "action_xml_id": "industry_fsm_report.fsm_worksheets_action_settings",
                    "worksheet_template_id": self.id,
                }
            )
        return context

    def get_x_model_form_action(self):
        action = super().get_x_model_form_action()
        if self.res_model == "project.task":
            action["context"].update(
                {
                    "action_xml_id": "industry_fsm_report.fsm_worksheets_action_settings",
                    "worksheet_template_id": self.id,
                }
            )
        return action

    @api.model
    def _create_demo_data_fsm(self, model_id=False) -> None:
        if not model_id:
            model_id = self.env.ref(
                "industry_fsm_report.fsm_worksheet_template2"
            ).model_id.id
        self.env["ir.model.fields"].with_context(
            _import_current_module="industry_fsm_report"
        ).create(
            [
                {
                    "id": "fsm_template_field1",
                    "name": "x_intervention_type",
                    "ttype": "selection",
                    "field_description": "Intervention Type",
                    "selection": "[('first_installation','First installation'),('technical_maintenance','Technical maintenance')]",
                    "model_id": model_id,
                },
                {
                    "id": "fsm_template_field2",
                    "name": "x_description",
                    "ttype": "text",
                    "field_description": "Description of the Intervention",
                    "model_id": model_id,
                },
                {
                    "id": "fsm_template_field3",
                    "name": "x_manufacturer",
                    "ttype": "many2one",
                    "relation": "res.partner",
                    "field_description": "Manufacturer",
                    "model_id": model_id,
                },
                {
                    "id": "fsm_template_field4",
                    "name": "x_checkbox",
                    "ttype": "boolean",
                    "field_description": "I hereby certify that this device meets the requirements of an acceptable device at the time of testing.",
                    "model_id": model_id,
                },
                {
                    "id": "fsm_template_field5",
                    "name": "x_serial_number",
                    "ttype": "char",
                    "field_description": "Serial Number",
                    "model_id": model_id,
                },
                {
                    "id": "fsm_template_field6",
                    "name": "x_date",
                    "ttype": "date",
                    "field_description": "Date",
                    "model_id": model_id,
                },
                {
                    "id": "fsm_template_field7",
                    "name": "x_worker_signature",
                    "ttype": "binary",
                    "field_description": "Technician Signature",
                    "model_id": model_id,
                },
            ]
        )
