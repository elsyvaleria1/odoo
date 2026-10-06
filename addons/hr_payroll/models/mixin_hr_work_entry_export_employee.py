from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time

from odoo import api, fields, models
from odoo.exceptions import RedirectWarning, ValidationError
from odoo.fields import Domain


@dataclass
class WorkEntryCollection:
    work_entries: models.Model
    duration: int


class MixinHrWorkEntryExportEmployee(models.AbstractModel):
    _name = "mixin.hr.work.entry.export.employee"
    _description = "Work Entry Export Employee"

    export_id = fields.Many2one(
        comodel_name="mixin.hr.work.entry.export",
        index=True,
        required=True,
        ondelete="cascade",
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
        ondelete="cascade",
        check_company=True,
    )
    version_ids = fields.Many2many(
        comodel_name="hr.version",
        compute="_compute_contract_ids",
        store=True,
        readonly=False,
        required=True,
        ondelete="cascade",
    )
    work_entry_ids = fields.Many2many(
        comodel_name="hr.work.entry",
        compute="_compute_work_entry_ids",
    )
    company_id = fields.Many2one(
        related="export_id.company_id",
        readonly=True,
    )

    @api.depends("employee_id")
    def _compute_contract_ids(self) -> None:
        contracts_by_employee = self.export_id._get_contracts_by_employee(
            employee_ids=self.employee_id.ids
        )
        for line in self:
            line.version_ids = contracts_by_employee.get(line.employee_id)

    @api.depends("export_id.period_start", "export_id.period_stop", "employee_id")
    def _compute_work_entry_ids(self) -> None:
        lines_by_export = defaultdict(lambda: self.env[self._name])
        for line in self:
            lines_by_export[line.export_id] += line
        for export, lines in lines_by_export.items():
            relevant_work_entries_by_employee = (
                export._get_relevant_work_entries_by_employee(
                    employee_ids=lines.employee_id.ids
                )
            )
            for line in lines:
                line.work_entry_ids = relevant_work_entries_by_employee.get(
                    line.employee_id
                )

    def _relations_to_check(self):
        """
        To be overridden in order to check for missing data in related fields.
        example:
        ```py
        def _relations_to_check(self):
            relations = super()._relations_to_check()
            return relations + ["employee_id.group_s_code"]
        ```

        :return: A list of the field to check in dot notation
        """
        return []

    def _check_data(self) -> None:
        def explore_and_check(path):
            base_record_path, field = path.rsplit(".", maxsplit=1)
            base_records = self.mapped(base_record_path)
            return base_records.filtered(lambda r: not r[field])

        messages = []
        for model_display_name, field_chain in self._relations_to_check():
            if problematic_records := explore_and_check(field_chain):
                parts = field_chain.split(".")
                parent_field, final_field_name = parts[-2], parts[-1]
                if parent_field == "version_ids":
                    readable_labels = [
                        f"{rec.employee_id.name} – {rec.display_name}"
                        for rec in problematic_records
                    ]
                else:
                    readable_labels = problematic_records.mapped("display_name")
                final_field_name = field_chain.rsplit(".", maxsplit=1)[-1]
                field_display_name = problematic_records._fields[
                    final_field_name
                ].string
                record_names = "\n    • ".join(readable_labels)

                message = self.env._(
                    "The following %(model_name)s are missing a %(field_name)s:\n    • %(names)s",
                    model_name=model_display_name,
                    field_name=field_display_name,
                    names=record_names,
                )
                messages.append(message)

        if messages:
            raise ValidationError("\n\n".join(messages))

    def _get_work_entries_by_day_and_code(self, limit_start=None, limit_stop=None):
        """Group work entries by day and code.

        :return: A defaultdict {date: defaultdict {code: WorkEntryCollection {work_entries, duration}}}
        """
        self.check_singleton()
        work_entries_by_day_and_code = defaultdict(
            lambda: defaultdict(
                lambda: WorkEntryCollection(
                    work_entries=self.env["hr.work.entry"],
                    duration=0,
                )
            )
        )
        for work_entry in self.work_entry_ids:
            date = work_entry.date
            code = work_entry.work_entry_type_id.code
            work_entries_by_day_and_code[date][code].work_entries |= work_entry
            work_entries_by_day_and_code[date][code].duration += (
                work_entry.duration * 3600
            )
        return work_entries_by_day_and_code

    def _check_work_entries(self) -> None:
        if any(work_entry.state == "conflict" for work_entry in self.work_entry_ids):
            base_domain = Domain("employee_id", "in", self.employee_id.ids) & Domain(
                "state", "=", "conflict"
            )
            time_domain = Domain.OR(
                Domain(
                    "date_start", ">=", datetime.combine(export.period_start, time.min)
                )
                & Domain(
                    "date_start", "<=", datetime.combine(export.period_stop, time.max)
                )
                for export in self.export_id
            )

            raise RedirectWarning(
                message=self.env._(
                    "Some work entries are in conflict. Please resolve the conflicts before exporting."
                ),
                action=self.env.ref("hr_work_entry.hr_work_entry_action_conflict").id,
                button_text=self.env._("Resolve Conflicts"),
                additional_context={"domain": Domain.AND([base_domain, time_domain])},
            )

    def action_view_work_entries(self):
        self.check_singleton()
        return {
            "name": self.env._(
                "Work Entries for %(employee)s", employee=self.employee_id.name
            ),
            "res_model": self.work_entry_ids._name,
            "type": "ir.actions.act_window",
            "view_mode": "gantt,calendar,list,pivot,form",
            "domain": [("id", "in", self.work_entry_ids.ids)],
        }
