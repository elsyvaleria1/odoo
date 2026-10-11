from lxml import etree

from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBoardArchPreprocessing(TransactionCase):

    def _process(self, arch):
        return self.env["board.board"]._arch_preprocessing(arch)

    def test_sets_board_js_class(self):
        root = etree.fromstring(self._process("<form><board/></form>"))
        self.assertEqual(root.get("js_class"), "board")

    def test_arch_without_actions_preserved(self):
        root = etree.fromstring(self._process("<form><board><column/></board></form>"))
        self.assertEqual(root.get("js_class"), "board")
        self.assertEqual(len(root.findall(".//column")), 1)
        self.assertEqual(root.findall(".//action"), [])


@tagged("post_install", "-at_install")
class TestBoardGetView(TransactionCase):

    def test_get_view_without_custom_view(self):
        board_view = self.env.ref("board.board_my_dash_view")
        res = self.env["board.board"].get_view(board_view.id, "form")
        self.assertNotIn("custom_view_id", res)
        root = etree.fromstring(res["arch"])
        self.assertEqual(root.get("js_class"), "board")

    def test_get_view_merges_custom_view(self):
        custom_arch = "<form><board><column><action name='1' string='Kept'/></column></board></form>"
        board_view = self.env.ref("board.board_my_dash_view")
        custom_view = self.env["ir.ui.view.custom"].create(
            {
                "user_id": self.env.uid,
                "ref_id": board_view.id,
                "arch": custom_arch,
            }
        )

        res = self.env["board.board"].get_view(board_view.id, "form")

        self.assertEqual(res["custom_view_id"], custom_view.id)
        root = etree.fromstring(res["arch"])
        self.assertEqual(root.get("js_class"), "board")
        self.assertEqual([a.get("name") for a in root.findall(".//action")], ["1"])

    def test_get_view_ignores_other_users_custom_view(self):
        board_view = self.env.ref("board.board_my_dash_view")
        other_user = self.env["res.users"].create(
            {
                "name": "Board Other User",
                "login": "board_other_user",
            }
        )
        self.env["ir.ui.view.custom"].create(
            {
                "user_id": other_user.id,
                "ref_id": board_view.id,
                "arch": "<form><board><column/></board></form>",
            }
        )

        res = self.env["board.board"].get_view(board_view.id, "form")

        self.assertNotIn("custom_view_id", res)


@tagged("post_install", "-at_install")
class TestBoardAddToDashboard(HttpCase):

    def test_add_to_dashboard(self):
        self.authenticate("admin", "admin")
        board_view = self.env.ref("board.board_my_dash_view")

        result = self.call_jsonrpc(
            "/board/add_to_dashboard",
            {
                "action_id": board_view.id,
                "context_to_save": {"allowed_company_ids": [1]},
                "domain": [],
                "view_mode": "list",
                "name": "Test Dashboard Item",
            },
        )

        self.assertTrue(result)
        custom_view = self.env["ir.ui.view.custom"].search(
            [
                ("user_id", "=", self.env.ref("base.user_admin").id),
                ("ref_id", "=", board_view.id),
            ]
        )
        self.assertTrue(custom_view)
        root = etree.fromstring(custom_view.arch)
        action = root.find(".//action")
        self.assertIsNotNone(action)
        self.assertEqual(action.get("name"), str(board_view.id))
        self.assertEqual(action.get("string"), "Test Dashboard Item")
        self.assertNotIn("allowed_company_ids", action.get("context"))

    def test_add_to_dashboard_without_action_id_returns_false(self):
        self.authenticate("admin", "admin")

        result = self.call_jsonrpc(
            "/board/add_to_dashboard",
            {
                "action_id": False,
                "context_to_save": {},
                "domain": [],
                "view_mode": "list",
                "name": "Should Not Save",
            },
        )

        self.assertFalse(result)
