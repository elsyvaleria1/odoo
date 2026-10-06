from odoo.tests.common import TransactionCase


class ResourceCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Second Pass Co"})
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "SP calendar", "company_id": cls.company.id, "tz": "UTC"}
        )

    def _resource(self, **vals):
        return self.env["resource.resource"].create(
            {
                "name": vals.pop("name", "SP resource"),
                "company_id": vals.pop("company_id", self.company.id),
                "calendar_id": vals.pop("calendar_id", self.calendar.id),
                "tz": vals.pop("tz", "UTC"),
                **vals,
            }
        )
