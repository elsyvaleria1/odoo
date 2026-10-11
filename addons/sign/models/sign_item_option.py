from collections.abc import Iterable

from odoo import api, fields, models


class SignItemOption(models.Model):
    _name = "sign.item.option"
    _description = "Option of a selection Field"
    _rec_name = "value"

    value = fields.Text(
        string="Option",
        readonly=True,
    )

    _value_uniq = models.Constraint(
        "unique (value)",
        "Value already exists!",
    )

    @api.model
    def get_or_create_option_ids(self, options: Iterable[str]) -> list[int]:
        options = list(dict.fromkeys(options))
        existing = {
            option.value: option.id
            for option in self.search([("value", "in", options)])
        }
        missing = [value for value in options if value not in existing]
        for option in self.create([{"value": value} for value in missing]):
            existing[option.value] = option.id
        return [existing[value] for value in options]
