from odoo.tests import TransactionCase


class TestGanttData(TransactionCase):
    """Cover the get_gantt_data payload contract on a plain model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parent = cls.env["res.partner"].create({"name": "Gantt Parent"})
        cls.child = cls.env["res.partner"].create(
            {
                "name": "Gantt Child",
                "parent_id": cls.parent.id,
            }
        )
        cls.partners = cls.parent | cls.child
        cls.spec = {"display_name": {}}

    def _domain(self):
        return [("id", "in", self.partners.ids)]

    def test_gantt_data_without_groupby_returns_single_group(self):
        """Without groupby every record lands in one synthetic group."""
        result = self.env["res.partner"].get_gantt_data(self._domain(), [], self.spec)

        self.assertEqual(result["length"], 1)
        self.assertEqual(len(result["groups"]), 1)
        expected_ids = self.env["res.partner"].search(self._domain()).ids
        self.assertEqual(result["groups"][0]["__record_ids"], expected_ids)
        self.assertEqual(
            sorted(record["id"] for record in result["records"]),
            sorted(self.partners.ids),
        )

    def test_gantt_data_without_groupby_hides_internal_keys(self):
        """The raw aggregate and extra domain never reach the client payload."""
        result = self.env["res.partner"].get_gantt_data(self._domain(), [], self.spec)

        group = result["groups"][0]
        self.assertNotIn("id:array_agg", group)
        self.assertNotIn("__extra_domain", group)

    def test_gantt_data_grouped_splits_records_per_group(self):
        """Grouping by a many2one distributes the records over its values."""
        result = self.env["res.partner"].get_gantt_data(
            self._domain(), ["parent_id"], self.spec
        )

        self.assertEqual(result["length"], 2)
        # The grouped branch strips the internal keys of every real
        # read_group result, __fold included.
        for group in result["groups"]:
            self.assertNotIn("id:array_agg", group)
            self.assertNotIn("__extra_domain", group)
            self.assertNotIn("__fold", group)
        ids_per_group = {
            group["parent_id"][0] if group["parent_id"] else False: group[
                "__record_ids"
            ]
            for group in result["groups"]
        }
        self.assertEqual(ids_per_group[self.parent.id], [self.child.id])
        self.assertEqual(ids_per_group[False], [self.parent.id])

    def test_gantt_data_empty_domain_returns_empty_group(self):
        """A domain matching nothing still returns the one-group envelope."""
        result = self.env["res.partner"].get_gantt_data([("id", "=", 0)], [], self.spec)

        self.assertEqual(result["length"], 1)
        self.assertEqual(result["groups"][0]["__record_ids"], [])
        self.assertEqual(result["records"], [])

    def test_gantt_data_progress_bar_and_unavailability_hooks_are_empty(self):
        """The base hooks answer per requested field with an empty mapping."""
        result = self.env["res.partner"].get_gantt_data(
            self._domain(),
            ["parent_id"],
            self.spec,
            unavailability_fields=["parent_id"],
            progress_bar_fields=["parent_id"],
            start_date="2026-01-01 00:00:00",
            stop_date="2026-12-31 00:00:00",
            scale="month",
        )

        self.assertEqual(result["progress_bars"], {"parent_id": {}})
        self.assertEqual(result["unavailabilities"], {"parent_id": {}})
