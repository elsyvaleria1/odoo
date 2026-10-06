import datetime

from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _get_expiration_date_from(self, from_date=None):
        if not self.use_expiration_date:
            return False
        self.check_singleton()
        from_date = from_date or fields.Datetime.today()
        return from_date + datetime.timedelta(days=self.expiration_time)
