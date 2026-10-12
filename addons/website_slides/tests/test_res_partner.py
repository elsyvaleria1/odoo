from odoo.exceptions import UserError

from . import common


class TestResPartner(common.SlidesCase):
    def test_slide_channel_count_updates_within_transaction(self):
        partner = self.env["res.partner"].create({"name": "New Enrollee"})
        self.assertEqual(partner.slide_channel_count, 0)

        self.channel._action_add_members(partner)

        self.assertEqual(partner.slide_channel_count, 1)
        self.assertIn(self.channel, partner.slide_channel_ids)

    def test_search_slide_channel_ids_finds_members(self):
        partner = self.env["res.partner"].create({"name": "Searchable Enrollee"})
        self.channel._action_add_members(partner)

        found = self.env["res.partner"].search(
            [("slide_channel_ids", "in", self.channel.ids)]
        )
        self.assertIn(partner, found)

        not_member = self.env["res.partner"].create({"name": "Non Member"})
        not_found = self.env["res.partner"].search(
            [("slide_channel_ids", "in", self.channel.ids)]
        )
        self.assertNotIn(not_member, not_found)

    def test_merging_two_attendees_of_one_course_keeps_their_progress(self):
        kept, merged = self.env["res.partner"].create(
            [{"name": "Attendee Kept"}, {"name": "Attendee Merged Away"}]
        )
        self.channel._action_add_members(kept + merged)
        membership = self.channel.channel_partner_all_ids.filtered(
            lambda member: member.partner_id == merged
        )
        membership.completion = 60
        with self.assertRaisesRegex(UserError, "would duplicate"):
            self.env["wizard.res.partner.merge"].create({})._merge(
                (kept + merged).ids, kept
            )
        self.assertTrue(merged.exists())
        self.assertTrue(membership.exists())
        self.assertEqual(membership.completion, 60)
