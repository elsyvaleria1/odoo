from odoo.tests.common import TransactionCase


class TestDateRangeSearchMixin(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.lang = "en_US"
        rtype = cls.env["date.range.type"].create(
            {"name": __name__, "company_id": False, "allow_overlap": False},
        )
        cls.env["wizard.date.range.create"].create(
            {
                "date_start": "1943-01-01",
                "name_prefix": "1943-",
                "type_id": rtype.id,
                "duration_count": 3,
                "duration_unit": "month",
                "count": 4,
            },
        ).action_apply()
        cls.ranges = cls.env["date.range"].search([("type_id", "=", rtype.id)])
        cls.model = cls.env["date.range.search.test"]

    def test_01_search_view(self):
        self.assertIn(
            '<separator/><field name="date_range_search_id" string="Period"/>',
            self.model.get_view(view_type="search")["arch"],
        )
        self.assertNotIn(
            '<separator/><field name="date_range_search_id" string="Period"/>',
            self.model.get_view(view_type="form")["arch"],
        )
        view = self.env["ir.ui.view"].create(
            {
                "name": __name__,
                "model": self.model._name,
                "arch": """
                <search>
                    <field name="name"/>
                    <group>
                        <filter name="group_by_name" string="Name"
                            context="{'group_by': 'name'}"/>
                    </group>
                </search>
            """,
            },
        )
        self.assertIn(
            '<separator/><field name="date_range_search_id" string="Period"/>',
            self.model.get_view(view_type="search")["arch"],
        )
        view.arch = """
            <search>
                <field name="name"/>
                <field name="date_range_search_id"/>
                <group>
                    <filter name="group_by_name" string="Name"
                        context="{'group_by': 'name'}"/>
                </group>
            </search>
        """
        self.assertNotIn(
            '<separator/><field name="date_range_search_id" string="Period"/>',
            self.model.get_view(view_type="search")["arch"],
        )

    def test_02_search_result(self):
        record = self.model.create({"test_date": "1943-04-05"})
        self.assertFalse(record.date_range_search_id)
        self.assertIn(
            record,
            self.model.search([("date_range_search_id", "=", self.ranges[1].id)]),
        )
        self.assertNotIn(
            record,
            self.model.search([("date_range_search_id", "!=", self.ranges[1].id)]),
        )
        self.assertIn(
            record,
            self.model.search([("date_range_search_id", "!=", self.ranges[0].id)]),
        )
        self.assertNotIn(
            record,
            self.model.search([("date_range_search_id", "=", self.ranges[0].id)]),
        )
        self.assertIn(
            record,
            self.model.search([("date_range_search_id", "in", self.ranges.ids)]),
        )
        self.assertNotIn(
            record,
            self.model.search([("date_range_search_id", "not in", self.ranges.ids)]),
        )
        self.assertIn(
            record,
            self.model.search([("date_range_search_id", "not in", self.ranges[3].ids)]),
        )
        self.assertNotIn(
            record,
            self.model.search([("date_range_search_id", "in", self.ranges[3].ids)]),
        )
        self.assertIn(
            record,
            self.model.search([("date_range_search_id", "ilike", "1943")]),
        )
        self.assertNotIn(
            record,
            self.model.search([("date_range_search_id", "not ilike", "1943")]),
        )
        self.assertIn(
            record,
            self.model.search([("date_range_search_id", "not ilike", "2021")]),
        )
        self.assertNotIn(
            record,
            self.model.search([("date_range_search_id", "ilike", "2021")]),
        )
        self.assertIn(record, self.model.search([("date_range_search_id", "=", True)]))
        self.assertNotIn(
            record,
            self.model.search([("date_range_search_id", "=", False)]),
        )
        self.assertIn(
            record,
            self.model.search([("date_range_search_id", "!=", False)]),
        )
        self.assertNotIn(
            record,
            self.model.search([("date_range_search_id", "!=", True)]),
        )

    def test_03_read(self):
        record = self.model.create({"test_date": "1943-04-05"})
        self.assertFalse(record.date_range_search_id)

    def test_04_load_views(self):
        view = self.model.get_views([(None, "form")])
        field = view["models"][self.model._name]["fields"]["date_range_search_id"]
        self.assertNotIn("technical", field["string"])
