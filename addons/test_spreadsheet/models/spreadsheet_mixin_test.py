from odoo import models


class SpreadsheetTest(models.Model):

    _description = "Dummy Spreadsheet"
    _name = "spreadsheet.test"
    _inherit = ["mixin.spreadsheet"]
