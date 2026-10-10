from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.base.tests.common import converted_reach
from odoo.addons.mail.tools.discuss import Store


@tagged("post_install", "-at_install")
class TestCannedResponseAdministrator(TransactionCase):
    def test_an_administrator_reaches_every_shared_response(self):
        author = new_test_user(
            self.env,
            login="canned_author",
            groups="base.group_user,base.group_erp_manager",
        )
        administrator = new_test_user(
            self.env,
            login="canned_administrator",
            groups="base.group_user,mail.group_mail_canned_response_admin",
        )
        Canned = self.env["mail.canned.response"].with_user(author)
        shared = Canned.create(
            {
                "source": "shared-elsewhere",
                "substitution": "Shared with the settings group",
                "group_ids": [self.env.ref("base.group_erp_manager").id],
            }
        )
        private = Canned.create({"source": "private", "substitution": "Only mine"})
        responses = (shared | private).sudo()

        self.assertEqual(
            responses.with_user(administrator).search([("id", "in", responses.ids)]),
            shared,
        )
        for operation in ("read", "write", "unlink"):
            with self.subTest(operation=operation):
                reached = converted_reach(
                    self.env, "mail.canned.response", administrator, operation
                )
                self.assertEqual(reached & responses, shared)

    def test_a_response_is_shared_with_internal_groups_only(self):
        Canned = self.env["mail.canned.response"]
        for xmlid in ("base.group_portal", "base.group_public"):
            with self.subTest(group=xmlid), self.assertRaises(ValidationError):
                Canned.create(
                    {
                        "source": "leaked",
                        "substitution": "Internal pricing notes",
                        "group_ids": [self.env.ref(xmlid).id],
                    }
                )

    def test_a_user_shares_only_with_groups_they_belong_to(self):
        author = new_test_user(
            self.env, login="canned_sharer", groups="base.group_user"
        )
        Canned = self.env["mail.canned.response"].with_user(author)
        with self.assertRaises(AccessError):
            Canned.create(
                {
                    "source": "elsewhere",
                    "substitution": "Pushed to a group I am not in",
                    "group_ids": [self.env.ref("base.group_system").id],
                }
            )
        mine = Canned.create(
            {
                "source": "among-us",
                "substitution": "Shared with my own group",
                "group_ids": [self.env.ref("base.group_user").id],
            }
        )
        with self.assertRaises(AccessError):
            mine.group_ids |= self.env.ref("base.group_system")


@tagged("post_install", "-at_install")
class TestCannedResponseBroadcast(TransactionCase):
    def test_the_group_a_response_leaves_is_told_to_drop_it(self):
        settings = self.env.ref("base.group_erp_manager")
        system = self.env.ref("base.group_system")
        response = self.env["mail.canned.response"].create(
            {"source": "moved", "substitution": "Moved", "group_ids": [settings.id]}
        )
        sent = []
        bus_send = Store.bus_send

        def spy(store, *args, **kwargs):
            sent.append((store.target.channel, store.get_result()))
            return bus_send(store, *args, **kwargs)

        with patch.object(Store, "bus_send", spy):
            response.group_ids = system

        dropped = [
            channel
            for channel, result in sent
            if any(
                row.get("_DELETE") and row["id"] == response.id
                for row in result.get("mail.canned.response", [])
            )
        ]
        self.assertIn(settings, dropped)

    def test_one_store_per_channel_however_many_responses(self):
        settings = self.env.ref("base.group_erp_manager")
        sent = []
        bus_send = Store.bus_send

        def spy(store, *args, **kwargs):
            sent.append(store.target.channel)
            return bus_send(store, *args, **kwargs)

        with patch.object(Store, "bus_send", spy):
            responses = self.env["mail.canned.response"].create(
                [
                    {
                        "source": f"batch-{index}",
                        "substitution": "Batched",
                        "group_ids": [settings.id],
                    }
                    for index in range(5)
                ]
            )
        self.assertEqual(sent.count(settings), 1, "one bus send per channel")
        self.assertEqual(len(sent), len(set(sent)))
        self.assertEqual(len(responses), 5)

    def test_a_share_group_is_never_broadcast_to(self):
        portal = self.env.ref("base.group_portal")
        portal_user = new_test_user(
            self.env, login="canned_portal", groups="base.group_portal"
        )
        response = self.env["mail.canned.response"].create(
            {"source": "legacy", "substitution": "Legacy"}
        )
        self.env.cr.execute(
            "INSERT INTO mail_canned_response_res_groups_rel"
            " (mail_canned_response_id, res_groups_id) VALUES (%s, %s)",
            [response.id, portal.id],
        )
        legacy = response.with_user(portal_user).sudo()
        legacy.invalidate_recordset(["group_ids"])
        self.assertIn(portal, legacy.group_ids, "sanity: a row from before the check")
        sent = []
        bus_send = Store.bus_send

        def spy(store, *args, **kwargs):
            sent.append(store.target.channel)
            return bus_send(store, *args, **kwargs)

        with patch.object(Store, "bus_send", spy):
            legacy._broadcast()
        self.assertTrue(sent, "sanity: the response is broadcast")
        self.assertNotIn(portal, sent)


@tagged("post_install", "-at_install")
class TestCannedResponseUsage(TransactionCase):
    def test_a_registered_use_is_read_back_in_the_same_transaction(self):
        response = self.env["mail.canned.response"].create(
            {"source": "usage", "substitution": "Used"}
        )
        self.assertFalse(response.last_used)
        response._register_usage([response.id])
        self.assertTrue(response.last_used)
