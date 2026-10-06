from odoo.tests import common, tagged


@tagged("voip", "post_install", "-at_install")
class TestVoipT9(common.TransactionCase):
    def test_t9_name_is_correctly_computed(self):
        """
        Tests that the "t9_name" field on res.partner is correctly computed.
        """
        xanto, eric, shrek, pangram, oenone = self.env["res.partner"].create(
            [
                {"name": "xanto du 93"},
                {"name": "(っ◔◡◔)っ ♥ Éric ♥"},
                {"name": "𝓈𝒽𝓇𝑒𝓀"},
                {"name": "The quick brown fox jumps over the lazy dog"},
                {"name": "Œnone"},
            ]
        )
        self.assertEqual(xanto.t9_name, " 92686 38 93")
        self.assertEqual(eric.t9_name, " xxxxxxx x 3742 x")
        self.assertEqual(shrek.t9_name, " 74735")
        self.assertEqual(
            pangram.t9_name, " 843 78425 27696 369 58677 6837 843 5299 364"
        )
        self.assertEqual(oenone.t9_name, " 636663")
