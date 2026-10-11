from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.digest.tests.common import TestDigestCommon


@tagged("post_install", "-at_install")
class TestLiveChatDigest(TestDigestCommon):
    @classmethod
    @mute_logger("odoo.models.unlink")
    def setUpClass(cls):
        super().setUpClass()

        other_partner = cls.env["res.partner"].create({"name": "Other Partner"})

        cls.channels = cls.env["discuss.channel"].create(
            [
                {
                    "name": "Channel 1",
                    "livechat_operator_id": cls.env.user.partner_id.id,
                    "channel_type": "livechat",
                },
                {
                    "name": "Channel 2",
                    "livechat_operator_id": cls.env.user.partner_id.id,
                    "channel_type": "livechat",
                },
                {
                    "name": "Channel 3",
                    "livechat_operator_id": other_partner.id,
                    "channel_type": "livechat",
                },
            ]
        )

        cls.env["rating.rating"].search([]).unlink()

        cls.env["rating.rating"].create(
            [
                {
                    "rated_partner_id": cls.env.user.partner_id.id,
                    "res_id": cls.channels[0].id,
                    "res_model_id": cls.env["ir.model"]._get("discuss.channel").id,
                    "consumed": True,
                    "rating": 5,
                },
                {
                    "rated_partner_id": cls.env.user.partner_id.id,
                    "res_id": cls.channels[0].id,
                    "res_model_id": cls.env["ir.model"]._get("discuss.channel").id,
                    "consumed": True,
                    "rating": 0,
                },
                {
                    "rated_partner_id": cls.env.user.partner_id.id,
                    "res_id": cls.channels[0].id,
                    "res_model_id": cls.env["ir.model"]._get("discuss.channel").id,
                    "consumed": True,
                    "rating": 3,
                },
                {
                    "rated_partner_id": cls.env.user.partner_id.id,
                    "res_id": cls.channels[0].id,
                    "res_model_id": cls.env["ir.model"]._get("discuss.channel").id,
                    "consumed": True,
                    "rating": 3,
                },
            ]
        )

    def test_kpi_livechat_rating_value(self):
        self.assertEqual(round(self.digest_1.kpi_livechat_rating_value, 2), 33.33)

    def test_kpi_livechat_rating_ignores_ratings_on_other_channel_types(self):
        group = self.env["discuss.channel"].create(
            {
                "name": "A group chat",
                "channel_type": "group",
            }
        )
        self.env["rating.rating"].create(
            [
                {
                    "rated_partner_id": self.env.user.partner_id.id,
                    "res_id": group.id,
                    "res_model_id": self.env["ir.model"]._get("discuss.channel").id,
                    "consumed": True,
                    "rating": 1,
                }
            ]
            * 5
        )
        self.digest_1.invalidate_recordset(["kpi_livechat_rating_value"], flush=False)
        self.assertEqual(
            round(self.digest_1.kpi_livechat_rating_value, 2),
            33.33,
            "five bad ratings on a group chat must not move the livechat KPI",
        )

    def test_kpi_livechat_rating_does_not_materialise_every_channel(self):
        Channel = self.env["discuss.channel"]
        seen = []
        original = type(Channel).search

        def _record(records, *args, **kwargs):
            seen.append(args[0] if args else kwargs.get("domain"))
            return original(records, *args, **kwargs)

        with patch.object(type(Channel), "search", _record):
            self.digest_1.invalidate_recordset(
                ["kpi_livechat_rating_value"], flush=False
            )
            self.digest_1.kpi_livechat_rating_value

        self.assertFalse(
            [d for d in seen if d and ("channel_type", "=", "livechat") in list(d)],
            f"the KPI searched discuss.channel instead of subquerying it: {seen}",
        )

    def test_rating_domain_accepts_a_query(self):
        Channel = self.env["discuss.channel"]
        by_ids = Channel.search([("channel_type", "=", "livechat")]).rating_get_grades()
        by_query = Channel.rating_get_grades(
            record_ids=Channel._search([("channel_type", "=", "livechat")]),
        )
        self.assertEqual(by_ids, by_query)
        self.assertTrue(sum(by_ids.values()), "the fixture must produce some grades")
