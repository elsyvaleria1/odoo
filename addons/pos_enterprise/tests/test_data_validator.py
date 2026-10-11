from odoo.tests.common import TransactionCase

from odoo.addons.pos_enterprise.models.data_validator import list_of, object_of


class TestDataValidator(TransactionCase):
    def test_object_of_accepts_matching_object(self):
        validator = object_of({"name": True, "qty": True})
        valid, error = validator({"name": "burger", "qty": 2})
        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_object_of_rejects_non_dict(self):
        validator = object_of({"name": True})
        valid, error = validator(["not", "a", "dict"])
        self.assertFalse(valid)
        self.assertEqual(error, "not an object")

    def test_object_of_reports_missing_required_key(self):
        validator = object_of({"name": True, "qty": True})
        valid, error = validator({"name": "burger"})
        self.assertFalse(valid)
        self.assertEqual(error, "Missing key 'qty'")

    def test_object_of_runs_nested_validator(self):
        validator = object_of({"lines": list_of(object_of({"id": True}))})
        valid, error = validator({"lines": [{"id": 1}, {"id": 2}]})
        self.assertTrue(valid)
        self.assertIsNone(error)
        valid, error = validator({"lines": [{"id": 1}, {}]})
        self.assertFalse(valid)
        self.assertEqual(error, "Missing key 'id'")

    def test_list_of_accepts_any_list_with_true_schema(self):
        validator = list_of(True)
        valid, error = validator([1, "a", {"x": 1}])
        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_list_of_rejects_non_list(self):
        validator = list_of(True)
        valid, error = validator({"not": "a list"})
        self.assertFalse(valid)
        self.assertEqual(error, "not a list")

    def test_list_of_validates_each_item(self):
        seen = []

        def spy(item):
            seen.append(item)
            return item == "ok", "bad item"

        validator = list_of(spy)
        valid, error = validator(["ok", "oops", "never scanned"])
        self.assertFalse(valid)
        self.assertEqual(error, "bad item")
        self.assertEqual(seen, ["ok", "oops"], "the scan stops at the failure")

    def test_list_of_empty_list_is_valid(self):
        validator = list_of(object_of({"id": True}))
        valid, error = validator([])
        self.assertTrue(valid)
        self.assertIsNone(error)
