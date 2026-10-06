from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SpreadsheetContributor(models.Model):
    _name = "spreadsheet.contributor"
    _description = "Spreadsheet Contributor"
    _rec_name = "user_id"

    document_id = fields.Many2one(comodel_name="document.document")
    user_id = fields.Many2one(comodel_name="res.users")
    last_update_date = fields.Datetime(
        string="Last update date",
        default=fields.Datetime.now,
    )

    _spreadsheet_user_unique = models.Constraint(
        "unique (document_id, user_id)",
        "A combination of the spreadsheet and the user already exist",
    )

    @api.model
    def _update(self, user, document) -> None:
        record = self.search(
            [("user_id", "=", user.id), ("document_id", "=", document.id)]
        )
        _debug.logic(
            "spreadsheet_contributor_touched",
            user=user,
            document=document,
            action="refreshed" if record else "created",
        )
        if record:
            record.write({"last_update_date": fields.Datetime.now()})
        else:
            self.create(
                {
                    "document_id": document.id,
                    "user_id": user.id,
                }
            )
