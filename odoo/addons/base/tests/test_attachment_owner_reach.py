import random
from unittest.mock import patch

from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.base.tests.common import make_guard_row


@tagged("post_install", "-at_install")
class TestAttachmentOwnerReach(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login="reach_internal", groups="base.group_user"
        )
        company_b = cls.env["res.company"].create({"name": "Reach B"})
        cls.other = new_test_user(
            cls.env,
            login="reach_other",
            groups="base.group_user",
            company_id=company_b.id,
            company_ids=[(6, 0, company_b.ids)],
        )
        Partner = cls.env["res.partner"]
        cls.readable = Partner.create([{"name": f"reach-open-{i}"} for i in range(4)])
        cls.hidden = Partner.create(
            [
                {"name": f"reach-hidden-{i}", "company_id": company_b.id}
                for i in range(4)
            ]
        )
        cls.view = cls.env["ir.ui.view"].search([], limit=1)
        Attachment = cls.env["ir.attachment"]
        rng = random.Random(11)
        owners = [("res.partner", p.id) for p in cls.readable | cls.hidden]
        owners.append(("ir.ui.view", cls.view.id))
        rows = []
        for i in range(60):
            kind = rng.randrange(5)
            values = {"name": f"reach-{i}", "raw": b"x"}
            if kind < 3:
                values["res_model"], values["res_id"] = rng.choice(owners)
            elif kind == 3 and rows:
                values["res_model"], values["res_id"] = (
                    "ir.attachment",
                    rng.choice(rows),
                )
            values["public"] = rng.random() < 0.15
            author = rng.choice([cls.env.user, cls.user, cls.other])
            rows.append(Attachment.with_user(author).sudo().create(values).id)
        cls.attachments = Attachment.browse(rows)
        make_guard_row(
            cls.env,
            "ir.attachment",
            f"[('id', 'not in', {rows[:5]})]",
            operation="r",
            name="hide some owner attachments",
        )
        cls.env.flush_all()

    def checked(self, Attachments, ids):
        return Attachments.browse(ids)._filtered_access("read").ids

    @mute_logger("odoo.addons.base.models.ir_access", "odoo.models")
    def test_every_search_path_finds_what_the_check_reads(self):
        ordered = self.attachments.sorted("id", reverse=True).ids
        for user in (self.user, self.other):
            Attachments = self.env["ir.attachment"].with_user(user)
            expected = self.checked(Attachments, ordered)
            name = [("name", "=like", "reach-%")]
            with self.subTest(user=user.login, path="unbounded"):
                self.assertEqual(Attachments.search(name).ids, expected)
                self.assertEqual(Attachments.search_count(name), len(expected))
            with self.subTest(user=user.login, path="pages by chunks"):
                with self.patch_chunk(4):
                    pages = [
                        Attachments.search(name, offset=offset, limit=7).ids
                        for offset in range(0, len(ordered), 7)
                    ]
                self.assertEqual([i for page in pages for i in page], expected)
            with self.subTest(user=user.login, path="by ids"):
                for start in range(0, len(ordered), 13):
                    slice_ids = ordered[start : start + 13]
                    self.assertEqual(
                        Attachments.search([("id", "in", slice_ids)]).ids,
                        self.checked(Attachments, slice_ids),
                    )
            for res_model in ("res.partner", "ir.attachment", "ir.ui.view"):
                with self.subTest(user=user.login, path=f"pinned to {res_model}"):
                    pinned = name + [("res_model", "=", res_model)]
                    self.assertEqual(
                        Attachments.search(pinned).ids,
                        self.checked(
                            Attachments,
                            self.attachments.filtered(
                                lambda a, m=res_model: a.res_model == m
                            )
                            .sorted("id", reverse=True)
                            .ids,
                        ),
                    )

    @mute_logger("odoo.addons.base.models.ir_access", "odoo.models")
    def test_an_unreadable_owner_model_reaches_nothing(self):
        self.env["ir.access"].search(
            [
                ("model_id.model", "=", "ir.ui.view"),
                ("kind", "=", "permission"),
                ("for_read", "=", True),
            ]
        ).active = False
        self.env.flush_all()
        self.env.registry.clear_cache()
        self.addCleanup(self.env.registry.clear_cache)
        Attachments = self.env["ir.attachment"].with_user(self.user)
        on_view = self.attachments.filtered(lambda a: a.res_model == "ir.ui.view")
        found = Attachments.search([("id", "in", on_view.ids)])
        self.assertEqual(found.ids, self.checked(Attachments, found.ids))
        self.assertEqual(set(found.ids), set(self.checked(Attachments, on_view.ids)))
        self.assertFalse(found.filtered(lambda a: not a.sudo().public))

    def patch_chunk(self, size):
        return patch("odoo.tools.owner_reach.CHUNK", size)
