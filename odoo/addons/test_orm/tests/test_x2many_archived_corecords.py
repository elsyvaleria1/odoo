from odoo.tests import TransactionCase, new_test_user


class TestX2manyArchivedCorecords(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        owner = cls.env["test_orm.domain.partner"].create({})
        live, archived = cls.env["test_orm.domain.tag"].create(
            [{"name": "live"}, {"name": "archived", "active": False}]
        )
        cls.archived = archived
        cls.items = cls.env["test_orm.domain.item"].create(
            [
                {
                    "name": "archived only",
                    "owner_id": owner.id,
                    "tag_ids": archived.ids,
                },
                {"name": "live only", "owner_id": owner.id, "tag_ids": live.ids},
                {"name": "none", "owner_id": owner.id},
            ]
        )

    def _assert_reads(self, domain, expected, items=None):
        items = self.items if items is None else items
        self.env.invalidate_all()
        scope = [("id", "in", items.ids), *domain]
        found = items.browse().search(scope)
        self.assertEqual(sorted(found.mapped("name")), expected, f"search {domain}")
        filtered = items.filtered_domain(domain)
        self.assertEqual(
            sorted(filtered.mapped("name")), expected, f"filtered_domain {domain}"
        )

    def test_an_id_list_counts_the_links_to_archived_corecords(self):
        archived = self.archived.ids
        self._assert_reads([("tag_ids", "in", archived)], ["archived only"])
        self._assert_reads([("tag_ids", "not in", archived)], ["live only", "none"])
        self._assert_reads([("tag_ids", "=", False)], ["none"])
        self._assert_reads([("tag_ids", "!=", False)], ["archived only", "live only"])

    def test_a_subdomain_searches_the_active_corecords(self):
        self._assert_reads([("tag_ids", "any", [("name", "!=", False)])], ["live only"])
        self._assert_reads([("tag_ids", "ilike", "e")], ["live only"])

    def test_a_subdomain_naming_active_searches_every_corecord(self):
        self._assert_reads(
            [("tag_ids", "any", [("active", "=", False)])], ["archived only"]
        )
        self._assert_reads(
            [("tag_ids", "not any", [("active", "=", False)])], ["live only", "none"]
        )

    def test_subdomains_deciding_archived_corecords_apart_are_not_merged(self):
        self._assert_reads(
            ["|", ("tag_ids.active", "=", False), ("tag_ids.active", "=", True)],
            ["archived only", "live only"],
        )
        self._assert_reads(
            [
                "|",
                ("tag_ids", "any", [("active", "=", False), ("name", "=", "zzz")]),
                ("tag_ids", "any", [("name", "=", "archived")]),
            ],
            [],
        )

    def test_a_subdomain_keeping_every_active_value_searches_every_corecord(self):
        self._assert_reads(
            [("tag_ids", "any", [("active", "in", [True, False])])],
            ["archived only", "live only"],
        )

    def test_a_user_reads_a_related_path_through_the_active_corecords_only(self):
        # a user's filtered_domain answers a related condition by searching:
        # that search kept the filtered items archived or not by turning
        # active_test off, which also counted the archived tag the path reads
        user = new_test_user(self.env, "related_reader", groups="base.group_user")
        items = self.items.with_user(user)
        self._assert_reads(
            [("tag_name", "not in", ["archived"])],
            ["archived only", "live only", "none"],
            items,
        )
        self._assert_reads([("tag_name", "=", "archived")], [], items)
