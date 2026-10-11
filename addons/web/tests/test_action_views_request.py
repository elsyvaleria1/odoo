from odoo.tests import BaseCase, tagged

from ..controllers.action import _views_request


@tagged("post_install", "-at_install", "web_unit", "web_action")
class TestViewsRequest(BaseCase):
    """The views /web/action/load and /web/action/run fetch with an action."""

    @staticmethod
    def _views(search_view_id):
        action = {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "views": [[False, "list"]],
            "search_view_id": search_view_id,
        }
        return _views_request(action, {}, {}, {})["views"]

    def test_the_search_view_of_a_read_action(self):
        self.assertIn([7, "search"], self._views([7, "res.partner.search"]))

    def test_a_search_view_given_as_a_bare_id(self):
        self.assertIn([7, "search"], self._views(7))

    def test_no_search_view_takes_the_default(self):
        self.assertIn([False, "search"], self._views(False))
