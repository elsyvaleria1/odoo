from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestUtmMixinHelpers(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Mixin = cls.env["mixin.utm"]

    def test_split_name_without_counter(self):
        self.assertEqual(self.Mixin._split_name_and_count("Medium"), ("Medium", 1))

    def test_split_name_with_counter(self):
        self.assertEqual(
            self.Mixin._split_name_and_count("Medium [1234]"), ("Medium", 1234)
        )

    def test_find_or_create_is_idempotent(self):
        first = self.Mixin._get_or_create_record("utm.source", "Loop test source")
        second = self.Mixin._get_or_create_record("utm.source", "loop test source")
        self.assertEqual(first, second)

    def test_find_or_create_record_payload(self):
        payload = self.Mixin.get_or_create_record("utm.medium", "Loop test medium")
        self.assertIn("id", payload)
        self.assertEqual(payload["name"], "Loop test medium")

    def test_unique_names_increments_duplicates(self):
        result = self.Mixin._get_unique_names(
            "utm.source", ["ZZ uniq", "ZZ uniq", "ZZ uniq"]
        )
        self.assertEqual(result[0], "ZZ uniq")
        self.assertEqual(result[1], "ZZ uniq [2]")
        self.assertEqual(result[2], "ZZ uniq [3]")

    def test_empty_names_do_not_search_existing_records(self):
        with patch.object(
            self.env.registry["utm.source"],
            "search_read",
            side_effect=AssertionError("Empty names must not search all sources"),
        ):
            self.assertEqual(self.Mixin._get_unique_names("utm.source", []), [])
            self.assertEqual(
                self.Mixin._get_unique_names("utm.source", [None, False, ""]),
                [False, False, False],
            )

    def test_unique_names_preserve_input_and_empty_positions(self):
        names = [None, "Mixed source", False, "Mixed source", ""]
        original = names.copy()
        self.assertEqual(
            self.Mixin._get_unique_names("utm.source", names),
            [False, "Mixed source", False, "Mixed source [2]", False],
        )
        self.assertEqual(names, original)
