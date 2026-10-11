from odoo.tests import tagged

from odoo.addons.account_depreciation.tests.common import TestAccountAssetCommon


@tagged("post_install", "-at_install")
class TestDepreciationPostingLog(TestAccountAssetCommon):
    def test_posted_entries_are_noted_on_their_assets_in_one_insert(self):
        assets = self.env["account.depreciation.board"].concat(
            *(
                self.create_asset(value=600.0, periodicity="monthly", periods=6)
                for _index in range(3)
            )
        )
        assets.action_confirm()
        entries = self.env["account.move"].concat(
            *(asset.depreciation_move_ids[:1] for asset in assets)
        )
        self.assertEqual(set(entries.mapped("state")), {"posted"})
        noted_before = assets.message_ids

        with self.capturedQueries() as queries:
            entries._log_depreciation_asset()

        inserts = [query for query in queries if 'INSERT INTO "mail_message"' in query]
        self.assertEqual(len(inserts), 1)
        notes = assets.message_ids - noted_before
        self.assertEqual(len(notes), len(entries))
        for asset, entry in zip(assets, entries, strict=True):
            self.assertIn(entry.name, (asset.message_ids - noted_before).body)
        self.assertEqual(set(notes.mapped("message_type")), {"notification"})
        self.assertEqual(notes.subtype_id, self.env.ref("mail.mt_note"))

    def test_entries_of_one_asset_are_noted_in_their_order(self):
        asset = self.create_asset(value=600.0, periodicity="monthly", periods=6)
        asset.action_confirm()
        entries = asset.depreciation_move_ids.sorted("date")
        noted_before = asset.message_ids

        entries._log_depreciation_asset()

        notes = (asset.message_ids - noted_before).sorted("id")
        self.assertEqual(len(notes), len(entries))
        for note, entry in zip(notes, entries, strict=True):
            self.assertIn(entry.name, note.body)
