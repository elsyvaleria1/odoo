from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCodeTranslationReload(TransactionCase):
    def test_a_reload_that_loses_the_table_lock_keeps_the_translations(self):
        Translation = self.env["transifex.code.translation"]
        Translation.create(
            {"source": "Hello", "value": "Hello", "module": "base", "lang": "en_US"}
        )

        with patch.object(
            type(Translation), "_load_code_translations", return_value=False
        ):
            self.assertFalse(Translation.reload())

        self.assertEqual(Translation.search_count([("source", "=", "Hello")]), 1)
