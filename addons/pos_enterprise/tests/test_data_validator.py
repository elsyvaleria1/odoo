from odoo.tests.common import TransactionCase

from odoo.addons.pos_enterprise.models.data_validator import list_of, object_of


class TestDataValidator(TransactionCase):
    def test_object_of_accepts_matching_object(self):
        """Check that a dict holding all required keys validates."""
        validator = object_of({"name": True, "qty": True})
        valid, error = validator({"name": "burger", "qty": 2})
        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_object_of_rejects_non_dict(self):
        """Check that any non-dict payload is rejected with the generic message."""
        validator = object_of({"name": True})
        valid, error = validator(["not", "a", "dict"])
        self.assertFalse(valid)
        self.assertEqual(error, "not an object")

    def test_object_of_reports_missing_required_key(self):
        """Check that a missing required key is reported by name."""
        validator = object_of({"name": True, "qty": True})
        valid, error = validator({"name": "burger"})
        self.assertFalse(valid)
        self.assertEqual(error, "Missing key 'qty'")

    def test_object_of_runs_nested_validator(self):
        """Check that a callable schema value validates the nested payload and
        propagates the nested error."""
        validator = object_of({"lines": list_of(object_of({"id": True}))})
        valid, error = validator({"lines": [{"id": 1}, {"id": 2}]})
        self.assertTrue(valid)
        self.assertIsNone(error)
        valid, error = validator({"lines": [{"id": 1}, {}]})
        self.assertFalse(valid)
        self.assertEqual(error, "Missing key 'id'")

    def test_list_of_accepts_any_list_with_true_schema(self):
        """Check that list_of(True) accepts heterogeneous items."""
        validator = list_of(True)
        valid, error = validator([1, "a", {"x": 1}])
        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_list_of_rejects_non_list(self):
        """Check that any non-list payload is rejected."""
        validator = list_of(True)
        valid, error = validator({"not": "a list"})
        self.assertFalse(valid)
        self.assertEqual(error, "not a list")

    def test_list_of_validates_each_item(self):
        """Check that the item validator runs on every element and the first
        failure stops the scan."""
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
        """Check that an empty list validates against any item schema."""
        validator = list_of(object_of({"id": True}))
        valid, error = validator([])
        self.assertTrue(valid)
        self.assertIsNone(error)
