from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install", "web_tour", "web_favorite")
class TestFavorite(HttpCase):
    def test_favorite_management(self):
        self.patch(
            self.env.registry.get("ir.module.module"),
            "_order",
            "sequence desc, id desc",
        )
        category = self.env["ir.module.category"].create(
            {"name": "Favorite Tour Category", "sequence": -1}
        )
        self.env["ir.module.module"].search(
            [("application", "=", False)], order="id", limit=1
        ).write(
            {
                "sequence": 100000,
                "shortdesc": "Favorite Tour Module",
                "category_id": category.id,
            }
        )
        self.start_tour("/odoo/apps", "test_favorite_management", login="admin")
