
from odoo import fields, models


class DateRangeSearchTest(models.Model):
    _name = "date.range.search.test"
    _description = "Date Range Search Mixin Test Model"
    _inherit = ["mixin.date.range.search"]
    _date_range_search_field = "test_date"

    name = fields.Char()
    test_date = fields.Date()
