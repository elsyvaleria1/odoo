from odoo import api, fields, models


class QualityCheckSpreadsheet(models.Model):
    _name = "quality.check.spreadsheet"
    _description = "Quality check spreadsheet"
    _inherit = ["mixin.spreadsheet"]

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    check_cell = fields.Char(
        string="Success cell",
        help="The check is successful if the success cell value is TRUE. If there are"
        " several sheets, specify which one you want to use (e.g. Sheet2!C4). If not "
        "specified, the first sheet is selected by default.",
    )

    def get_formview_action(self, access_uid=None):
        return self.action_view_spreadsheet()

    def action_view_spreadsheet(self):
        return {
            "type": "ir.actions.client",
            "tag": "action_spreadsheet_quality",
            "params": {
                "spreadsheet_id": self.id,
            },
        }

    def _get_spreadsheet_metadata(self, access_token=None):
        data = super()._get_spreadsheet_metadata(access_token)
        check = self.env["quality.check"].search(
            [("spreadsheet_id", "=", self.id)], limit=1
        )
        data["quality_check_display_name"] = check.display_name
        data["quality_check_cell"] = self.check_cell
        return data

    @api.autovacuum
    def _gc_spreadsheet_history(self) -> None:
        self.env["spreadsheet.revision"]._gc_revisions(
            [("res_model", "=", self._name)],
            inactivity_days=1,
        )
