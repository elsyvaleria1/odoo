from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSignItemOption(TransactionCase):
    def test_options_are_created_once_and_reused(self):
        options = self.env["sign.item.option"]
        first = options.browse(
            options.get_or_create_option_ids(["Census A", "Census B", "Census A"])
        )
        self.assertEqual(set(first.mapped("value")), {"Census A", "Census B"})
        second = options.browse(
            options.get_or_create_option_ids(["Census B", "Census C"])
        )
        self.assertEqual(set(second.mapped("value")), {"Census B", "Census C"})
        self.assertEqual(
            first & second, first.filtered(lambda option: option.value == "Census B")
        )
        self.assertEqual(
            options.search_count(
                [("value", "in", ["Census A", "Census B", "Census C"])]
            ),
            3,
        )

    def test_empty_options_create_nothing(self):
        options = self.env["sign.item.option"]
        count = options.search_count([])
        self.assertEqual(options.get_or_create_option_ids([]), [])
        self.assertEqual(options.search_count([]), count)

    def test_options_keep_exact_values(self):
        options = self.env["sign.item.option"]
        values = ["Census", " census ", "Cénsüs"]
        records = options.browse(options.get_or_create_option_ids(iter(values)))
        self.assertEqual(set(records.mapped("value")), set(values))
