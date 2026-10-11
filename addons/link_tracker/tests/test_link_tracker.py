from odoo.exceptions import UserError
from odoo.tests import common, tagged

from odoo.addons.link_tracker.tests.common import MockLinkTracker


@tagged("link_tracker")
class TestLinkTracker(common.TransactionCase, MockLinkTracker):
    def setUp(self):
        super().setUp()
        self._web_base_url = "https://test.odoo.com"
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", self._web_base_url
        )

    def test_absolute_url(self):
        link_tracker = self.env["link.tracker"].create(
            {
                "url": "https://odoo.com",
                "title": "Odoo",
            }
        )
        self.assertEqual(link_tracker.absolute_url, link_tracker.url)

        link_tracker.write({"url": "odoo"})
        self.assertEqual(link_tracker.url, "http://odoo")
        self.assertEqual(link_tracker.absolute_url, "http://odoo")

        link_tracker.write({"url": "/odoo"})
        self.assertEqual(link_tracker.url, "/odoo")
        self.assertEqual(link_tracker.absolute_url, f"{self._web_base_url}/odoo")

    def test_create(self):
        link_trackers = self.env["link.tracker"].create(
            [
                {
                    "url": "odoo.com",
                    "title": "Odoo",
                },
                {
                    "url": "example.com",
                    "title": "Odoo",
                },
                {
                    "url": "http://test.example.com",
                    "title": "Odoo",
                },
            ]
        )

        self.assertEqual(
            link_trackers.mapped("url"),
            ["http://odoo.com", "http://example.com", "http://test.example.com"],
        )

        self.assertEqual(len(set(link_trackers.mapped("code"))), 3)

    def test_search_or_create(self):
        values_1, values_2, values_3 = [
            {"url": "https://odoo.com", "title": "Odoo"},
            {"url": "https://odoo.be", "title": "Odoo"},
            {
                "url": "https://odoo.com",
                "title": "Odoo New",
                "label": "New one!",
            },
        ]
        expected_values_1, expected_values_2, expected_values_3 = [
            {
                "campaign_id": self.env["utm.campaign"],
                "label": False,
                "medium_id": self.env["utm.medium"],
                "source_id": self.env["utm.source"],
                "title": "Odoo",
                "url": "https://odoo.com",
            },
            {
                "campaign_id": self.env["utm.campaign"],
                "label": False,
                "medium_id": self.env["utm.medium"],
                "source_id": self.env["utm.source"],
                "title": "Odoo",
                "url": "https://odoo.be",
            },
            {
                "campaign_id": self.env["utm.campaign"],
                "label": "New one!",
                "medium_id": self.env["utm.medium"],
                "source_id": self.env["utm.source"],
                "title": "Odoo New",
                "url": "https://odoo.com",
            },
        ]
        link_tracker_1 = self.env["link.tracker"].create(values_1)
        link_tracker_1_dupe = self.env["link.tracker"].search_or_create([values_1])
        self.assertEqual(link_tracker_1, link_tracker_1_dupe)
        for fname, value in expected_values_1.items():
            self.assertEqual(link_tracker_1[fname], value)

        link_tracker_2 = self.env["link.tracker"].search_or_create([values_2])
        self.assertNotEqual(link_tracker_1, link_tracker_2)
        for fname, value in expected_values_2.items():
            self.assertEqual(link_tracker_2[fname], value)

        vals_456 = [values_2, values_3, values_1]
        link_tracker_4, link_tracker_5, link_tracker_6 = self.env[
            "link.tracker"
        ].search_or_create(vals_456)
        self.assertEqual(
            link_tracker_4, link_tracker_2, "Is coming from values_2, created before"
        )
        self.assertEqual(
            link_tracker_6, link_tracker_1, "Is coming from values_1, created before"
        )
        self.assertNotIn(
            link_tracker_5,
            link_tracker_1 + link_tracker_2,
            "Is a new one due to label diff",
        )
        for fname, value in expected_values_3.items():
            self.assertEqual(link_tracker_5[fname], value)

        link_tracker_7, link_tracker_8, link_tracker_9 = self.env[
            "link.tracker"
        ].search_or_create(vals_456)
        self.assertListEqual(
            (link_tracker_7 + link_tracker_8 + link_tracker_9).ids,
            (link_tracker_4 + link_tracker_5 + link_tracker_6).ids,
        )

        vals_3131 = [values_3, values_1, values_3, values_1]
        trackers_3131 = self.env["link.tracker"].search_or_create(vals_3131)
        self.assertListEqual(
            trackers_3131.ids,
            (link_tracker_5 + link_tracker_1 + link_tracker_5 + link_tracker_1).ids,
        )

        values_4 = {"url": "https://odoo.com", "label": "A different one"}
        vals_3434 = [values_3, values_4, values_3, values_4]
        trackers_3434 = self.env["link.tracker"].search_or_create(vals_3434)
        new_tracker = trackers_3434[1]
        self.assertListEqual(
            trackers_3434.ids,
            (link_tracker_5 + new_tracker + link_tracker_5 + new_tracker).ids,
        )

        values_5 = {"url": "https://odoo.com", "label": "Yet another label"}
        expected_values_5 = {
            "campaign_id": self.env["utm.campaign"],
            "label": "Yet another label",
            "medium_id": self.env["utm.medium"],
            "source_id": self.env["utm.source"],
            "title": "https://odoo.com",
            "url": "https://odoo.com",
        }
        vals_55 = [values_5, values_5]
        trackers_55 = self.env["link.tracker"].search_or_create(vals_55)
        new_tracker = trackers_55[0]
        self.assertListEqual(trackers_55.ids, (new_tracker + new_tracker).ids)
        for fname, value in expected_values_5.items():
            self.assertEqual(new_tracker[fname], value)

    def test_constraint(self):
        campaign_id = self.env["utm.campaign"].search([], limit=1)

        self.env["link.tracker"].create(
            {
                "url": "https://odoo.com",
                "title": "Odoo",
            }
        )

        link_1 = self.env["link.tracker"].create(
            {
                "url": "2nd url",
                "title": "Odoo",
                "campaign_id": campaign_id.id,
            }
        )
        self.assertEqual(link_1.label, False)

        with self.assertRaises(UserError):
            self.env["link.tracker"].create(
                {
                    "url": "https://odoo.com",
                    "title": "Odoo",
                }
            )

        with self.assertRaises(UserError):
            self.env["link.tracker"].create(
                {
                    "url": "https://odoo.com",
                    "title": "Odoo",
                    "label": "",
                }
            )

        with self.assertRaises(UserError):
            self.env["link.tracker"].create(
                {
                    "url": "2nd url",
                    "title": "Odoo",
                    "campaign_id": campaign_id.id,
                }
            )

        link_2 = self.env["link.tracker"].create(
            {
                "url": "2nd url",
                "title": "Odoo",
                "campaign_id": campaign_id.id,
                "medium_id": self.env["utm.medium"].search([], limit=1).id,
                "label": "",
            }
        )

        with self.assertRaises(UserError):
            (link_1 | link_2).write({"campaign_id": False, "medium_id": False})

        with self.assertRaises(UserError):
            (link_1 | link_2).write({"medium_id": False})

        link_1.label = "Something"
        (link_1 | link_2).write({"medium_id": False})

    def test_no_external_tracking(self):
        self.env["ir.config_parameter"].set_param(
            "link_tracker.no_external_tracking", "1"
        )

        campaign = self.env["utm.campaign"].create({"name": "campaign"})
        source = self.env["utm.source"].create({"name": "source"})
        medium = self.env["utm.medium"].create({"name": "medium"})

        expected_utm_params = {
            "utm_campaign": campaign.name,
            "utm_source": source.name,
            "utm_medium": medium.name,
        }

        link = self.env["link.tracker"].create(
            {
                "url": "http://external.com/test?a=example.com",
                "campaign_id": campaign.id,
                "source_id": source.id,
                "medium_id": medium.id,
                "title": "Title",
            }
        )
        self.assertLinkParams("http://external.com/test", link, {"a": "example.com"})

        link.url = f"{self._web_base_url}/test?a=example.com"
        self.assertLinkParams(
            f"{self._web_base_url}/test",
            link,
            {**expected_utm_params, "a": "example.com"},
        )

        link.url = "/test?a=example.com"

        self.assertLinkParams(
            "/test", link, {**expected_utm_params, "a": "example.com"}
        )

        self.env["ir.config_parameter"].set_param(
            "link_tracker.no_external_tracking", False
        )

        link.url = "http://external.com/test?a=example.com"
        self.assertLinkParams(
            "http://external.com/test",
            link,
            {**expected_utm_params, "a": "example.com"},
        )

    def test_no_loop(self):
        self.assertRaises(UserError, self.env["link.tracker"].create, {"url": "?"})
        self.assertRaises(
            UserError, self.env["link.tracker"].create, {"url": "?debug=1"}
        )
        self.assertRaises(UserError, self.env["link.tracker"].create, {"url": "#"})
        self.assertRaises(
            UserError,
            self.env["link.tracker"].create,
            {"url": "#model=project.task&id=3603607"},
        )

    def test_url_encoding(self):
        campaign = self.env["utm.campaign"].create({"name": "campai.gn..."})
        source = self.env["utm.source"].create({"name": "source..."})
        medium = self.env["utm.medium"].create({"name": "medium"})
        link = self.env["link.tracker"].create(
            {
                "url": "http://example.com",
                "title": "Odoo",
                "campaign_id": campaign.id,
                "source_id": source.id,
                "medium_id": medium.id,
            }
        )
        self.assertIn("utm_campaign=campai.gn%2E%2E%2E", link.redirected_url)
        self.assertIn("utm_source=source%2E%2E%2E", link.redirected_url)
        self.assertIn("utm_medium=medium", link.redirected_url)


    def test_code_follows_its_code_record(self):
        tracker = self.env["link.tracker"].create({"url": "https://code.example.com"})
        first = tracker.code
        self.assertTrue(first)

        self.env["link.tracker.code"].search(
            [("link_id", "=", tracker.id)]
        ).code = "renamed1"
        self.assertEqual(
            tracker.code, "renamed1", "renaming the code record must invalidate `code`"
        )
        self.assertTrue(tracker.short_url.endswith("/r/renamed1"))

        self.env["link.tracker.code"].create(
            {"code": "newer001", "link_id": tracker.id}
        )
        self.assertEqual(tracker.code, "newer001", "a newer code record must win")
        self.assertTrue(tracker.short_url.endswith("/r/newer001"))

    def test_code_given_at_creation_is_kept(self):
        tracker = self.env["link.tracker"].create(
            {
                "url": "https://given.example.com",
                "code": "chosen01",
            }
        )
        self.assertEqual(tracker.code, "chosen01")
        self.assertEqual(
            self.env["link.tracker.code"]
            .search([("link_id", "=", tracker.id)])
            .mapped("code"),
            ["chosen01"],
        )
        self.env.invalidate_all()
        self.assertEqual(tracker.code, "chosen01")
        self.assertEqual(
            self.env["link.tracker"].get_url_from_code("chosen01"),
            tracker.redirected_url,
        )

    def test_code_cleared_on_several_records(self):
        trackers = self.env["link.tracker"].create(
            [
                {"url": "https://multi-a.example.com"},
                {"url": "https://multi-b.example.com"},
            ]
        )
        codes = trackers.mapped("code")
        trackers.write({"code": False})
        self.env.invalidate_all()
        self.assertEqual(
            trackers.mapped("code"),
            codes,
            "clearing `code` leaves the issued codes alone",
        )

    def test_code_written_on_a_tracker_that_has_none(self):
        tracker = self.env["link.tracker"].create({"url": "https://orphan.example.com"})
        tracker.link_code_ids.unlink()
        self.env.invalidate_all()
        self.assertFalse(tracker.code)

        tracker.code = "issued01"
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(tracker.code, "issued01")
        self.assertEqual(
            self.env["link.tracker"].get_url_from_code("issued01"),
            tracker.redirected_url,
        )

    def test_generated_codes_are_unguessable(self):
        codes = self.env["link.tracker.code"]._get_random_code_strings(20)
        self.assertEqual(len(set(codes)), 20)
        for code in codes:
            self.assertGreaterEqual(
                len(code), 8, "a 3-character code space is enumerable in under an hour"
            )
            self.assertTrue(code.isalnum())


    def test_no_loop_on_our_own_short_url(self):
        tracker = self.env["link.tracker"].create({"url": "https://loop.example.com"})
        own_short_url = tracker.short_url

        with self.assertRaises(UserError):
            tracker.write({"url": own_short_url})
        with self.assertRaises(UserError):
            self.env["link.tracker"].create({"url": own_short_url})
        with self.assertRaises(UserError):
            self.env["link.tracker"].create({"url": f"/r/{tracker.code}"})

        other = self.env["link.tracker"].create(
            {"url": "https://elsewhere.example.com/r/abc"}
        )
        self.assertEqual(other.url, "https://elsewhere.example.com/r/abc")


    def test_redirected_url_follows_its_utms(self):
        campaign = self.env["utm.campaign"].create({"name": "First"})
        tracker = self.env["link.tracker"].create(
            {"url": "https://utm.example.com/p", "campaign_id": campaign.id}
        )
        self.assertIn("utm_campaign=First", tracker.redirected_url)

        campaign.name = "Renamed"
        self.assertIn(
            "utm_campaign=Renamed",
            tracker.redirected_url,
            "renaming the campaign must invalidate `redirected_url`",
        )

        other = self.env["utm.campaign"].create({"name": "Second"})
        tracker.campaign_id = other
        self.assertIn(
            "utm_campaign=Second",
            tracker.redirected_url,
            "changing the campaign must invalidate `redirected_url`",
        )


    def test_recent_links_rejects_an_unknown_sort(self):
        self.env["link.tracker"].create({"url": "https://recent.example.com"})
        self.assertEqual(len(self.env["link.tracker"].recent_links("newest", 10)), 1)
        with self.assertRaises(UserError):
            self.env["link.tracker"].recent_links("no-such-order", 10)

    def test_recent_links_reads_only_what_it_shows(self):
        self.env["link.tracker"].create({"url": "https://fields.example.com"})
        [row] = self.env["link.tracker"].recent_links("newest", 10)
        self.assertNotIn("link_click_ids", row)
        self.assertNotIn("redirected_url", row)
        self.assertIn("short_url", row)


    def test_create_does_not_reach_the_network(self):
        self.env["link.tracker"]._get_title_from_url.reset_mock()
        tracker = self.env["link.tracker"].create({"url": "https://title.example.com"})
        self.env["link.tracker"]._get_title_from_url.assert_not_called()
        self.assertEqual(tracker.title, "https://title.example.com")

        asked = (
            self.env["link.tracker"]
            .with_context(
                link_tracker_fetch_title=True,
            )
            .create({"url": "https://title2.example.com"})
        )
        self.assertEqual(asked.title, "Test_TITLE")

    def test_search_or_create_asked_for_titles_fetches_a_found_trackers_missing_one(
        self,
    ):
        vals = {"url": "https://found.example.com"}
        tracker = self.env["link.tracker"].create(dict(vals))
        self.assertEqual(tracker.title, tracker.url)

        found = (
            self.env["link.tracker"]
            .with_context(link_tracker_fetch_title=True)
            .search_or_create([dict(vals)])
        )
        self.assertEqual(found, tracker)
        self.assertEqual(tracker.title, "Test_TITLE")

        self.env["link.tracker"]._get_title_from_url.reset_mock()
        self.env["link.tracker"].search_or_create([dict(vals)])
        self.env["link.tracker"]._get_title_from_url.assert_not_called()

    def test_cron_update_titles_backfills(self):
        tracker = self.env["link.tracker"].create(
            {"url": "https://backfill.example.com"}
        )
        self.assertEqual(tracker.title, tracker.url)
        self.env["link.tracker"]._cron_update_titles()
        self.assertEqual(tracker.title, "Test_TITLE")


    def test_cron_clear_expired_ips(self):
        tracker = self.env["link.tracker"].create({"url": "https://ip.example.com"})
        click = self.env["link.tracker.click"].create(
            {"link_id": tracker.id, "ip": "1.2.3.4"}
        )
        Click = self.env["link.tracker.click"]

        Click._cron_clear_expired_ips()
        self.assertEqual(click.ip, "1.2.3.4")

        self.env["ir.config_parameter"].sudo().set_param(
            "link_tracker.click_ip_retention_days", "30"
        )
        Click._cron_clear_expired_ips()
        self.assertEqual(
            click.ip, "1.2.3.4", "a click younger than the retention is untouched"
        )

        self.env.cr.execute(
            "UPDATE link_tracker_click SET create_date = now() - interval '60 days' WHERE id = %s",
            (click.id,),
        )
        click.invalidate_recordset(["create_date"])
        Click._cron_clear_expired_ips()
        self.assertFalse(click.ip, "a click past the retention forgets its IP")
