from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from psycopg.errors import CheckViolation, RestrictViolation, SerializationFailure

from odoo import SUPERUSER_ID, api
from odoo.db import db_connect
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestResourceRelation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Relation = cls.env["resource.relation"]
        cls.resources = cls.env["resource.resource"].create(
            [
                {
                    "name": name,
                    "type": "material",
                    "tz": zone,
                    "calendar_id": False,
                }
                for name, zone in (
                    ("Assembly", "UTC"),
                    ("Component", "Asia/Tokyo"),
                    ("Other assembly", "Europe/Paris"),
                )
            ]
        )
        cls.parent, cls.member, cls.other = cls.resources
        cls.start = datetime(2026, 1, 1)
        cls.end = datetime(2026, 2, 1)

    def _relation(self, parent=None, member=None, **vals):
        return self.Relation.create(
            {
                "parent_id": (parent or self.parent).id,
                "member_id": (member or self.member).id,
                "date_start": self.start,
                **vals,
            }
        )

    def _members(self, parent, at=None, relation_type="contains"):
        Relation = self.env["resource.relation"].with_env(parent.env)
        return Relation.search(
            Relation._get_domain_live_relations(at, relation_type)
            + [("parent_id", "in", parent.ids)]
        ).member_id

    def test_components_keep_identity_capacity_clock_and_reservations(self):
        self.parent.capacity = 3
        self.member.capacity = 2
        relation = self._relation()
        self.assertEqual(self._members(self.parent, self.start), self.member)
        self.assertNotEqual(self.parent, self.member)
        self.assertEqual((self.parent.capacity, self.member.capacity), (3, 2))
        self.assertEqual((self.parent.tz, self.member.tz), ("UTC", "Asia/Tokyo"))
        self.env["resource.reservation"].create(
            {
                "name": "Component booking",
                "resource_id": self.member.id,
                "date_start": self.start,
                "date_end": self.end,
            }
        )
        self.assertTrue(self.member.reservation_ids)
        self.assertFalse(self.parent.reservation_ids)
        relation.date_end = self.end
        self.assertFalse(self._members(self.parent, self.end))
        self.assertTrue(self.member.reservation_ids)
        copy = self.parent.copy()
        self.assertFalse(copy.relation_ids)
        self.assertFalse(copy.membership_ids)

    def test_one_resource_can_contain_several_independent_members(self):
        self._relation()
        self._relation(member=self.other)
        self.assertEqual(
            set(self._members(self.parent, self.start).ids),
            {self.member.id, self.other.id},
        )

    def test_physical_handover_is_half_open(self):
        self._relation(date_end=self.end)
        self._relation(parent=self.other, date_start=self.end)
        self.assertFalse(self._members(self.parent, self.end))
        self.assertEqual(self._members(self.other, self.end), self.member)
        local_end = datetime(2026, 2, 1, 9, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.assertFalse(self._members(self.parent, local_end))
        self.assertEqual(self._members(self.other, local_end), self.member)

    def test_overlapping_physical_parents_are_refused(self):
        self._relation()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._relation(parent=self.other)

    def test_dependency_can_have_several_parents_and_is_separate_from_containment(self):
        self._relation()
        self._relation(relation_type="depends_on")
        self._relation(parent=self.other, relation_type="depends_on")
        self.assertEqual(
            self._members(self.other, self.start, "depends_on"), self.member
        )
        self.assertFalse(self._members(self.other, self.start))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._relation(relation_type="depends_on")

    def test_cycle_requires_common_time_across_the_entire_path(self):
        self._relation(date_end=self.end)
        self._relation(parent=self.member, member=self.other, date_end=self.end)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._relation(parent=self.other, member=self.parent, date_end=self.end)
        self._relation(parent=self.other, member=self.parent, date_start=self.end)

    def test_dependency_cycle_is_refused(self):
        self._relation(relation_type="depends_on")
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._relation(
                parent=self.member, member=self.parent, relation_type="depends_on"
            )

    def test_pairwise_overlap_without_common_instant_is_not_a_cycle(self):
        self._relation(date_end=datetime(2026, 1, 10))
        self._relation(
            parent=self.member,
            member=self.other,
            date_start=datetime(2026, 1, 5),
            date_end=datetime(2026, 1, 15),
        )
        self._relation(
            parent=self.other,
            member=self.parent,
            date_start=datetime(2026, 1, 10),
            date_end=datetime(2026, 1, 20),
        )

    def test_archived_relation_still_validates_when_reactivated(self):
        relation = self._relation(active=False)
        self._relation(parent=self.other)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            relation.active = True
        self.assertFalse(
            self._members(self.parent.with_context(active_test=False), self.start)
        )

    def test_unbounded_start_and_archived_resource_keep_history(self):
        self._relation(date_start=False, date_end=self.end)
        self.member.active = False
        self.assertEqual(self._members(self.parent, datetime(2020, 1, 1)), self.member)
        self.assertFalse(self._members(self.parent, self.end))

    @mute_logger("odoo.db.cursor")
    def test_invalid_self_and_empty_period_are_rejected(self):
        for vals in ({"member": self.parent}, {"date_end": self.start}):
            with (
                self.assertRaises((CheckViolation, ValidationError)),
                self.cr.savepoint(),
            ):
                self._relation(**vals)

    def test_change_of_members_and_dates_revalidates(self):
        relation = self._relation(date_end=self.end)
        other = self._relation(parent=self.other, date_start=self.end)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            other.date_start = self.start
        with self.assertRaises((CheckViolation, ValidationError)), self.cr.savepoint():
            relation.parent_id = self.member

    def test_cross_company_links_and_company_changes_are_refused(self):
        company = self.env["res.company"].create({"name": "Relation foreign company"})
        foreign = self.env["resource.resource"].create(
            {
                "name": "Foreign component",
                "type": "material",
                "company_id": company.id,
            }
        )
        with self.assertRaises((UserError, ValidationError)), self.cr.savepoint():
            self._relation(member=foreign)
        self._relation()
        with self.assertRaises((UserError, ValidationError)), self.cr.savepoint():
            self.member.company_id = company

    def test_shared_parent_does_not_expose_foreign_members(self):
        self.parent.company_id = False
        self._relation()
        company = self.env["res.company"].create({"name": "Hidden membership company"})
        foreign = self.env["resource.resource"].create(
            {
                "name": "Hidden component",
                "type": "material",
                "company_id": company.id,
            }
        )
        self._relation(member=foreign)
        reader = new_test_user(
            self.env, login="relation_reader", groups="base.group_user"
        )
        self.assertEqual(
            self._members(self.parent.with_user(reader), self.start),
            self.member.with_user(reader),
        )
        for operation in ("create", "write", "unlink"):
            with self.assertRaises(AccessError):
                self.Relation.with_user(reader).check_access(operation)

    def test_removing_relation_preserves_resource_identities(self):
        relation = self._relation()
        relation.unlink()
        self.assertEqual(self.resources.exists(), self.resources)

    @mute_logger("odoo.db.cursor")
    def test_concurrent_disjoint_edges_cannot_complete_a_cycle(self):
        # Existing B->C and D->A form two components. A->B and C->D have
        # disjoint endpoints, so locking just the new endpoints is insufficient.
        ids = []
        context = {"allowed_company_ids": [self.env.company.id]}
        try:
            with db_connect(self.env.cr.dbname).cursor() as seed_cr:
                seed = api.Environment(seed_cr, SUPERUSER_ID, context)
                nodes = seed["resource.resource"].create(
                    [
                        {"name": f"Graph race {uuid4()}", "type": "material"}
                        for _ in range(4)
                    ]
                )
                ids = nodes.ids
                a, b, c, d = ids
                seed["resource.relation"].create(
                    [
                        {
                            "parent_id": b,
                            "member_id": c,
                            "relation_type": "depends_on",
                            "date_start": False,
                        },
                        {
                            "parent_id": d,
                            "member_id": a,
                            "relation_type": "depends_on",
                            "date_start": False,
                        },
                    ]
                )
                seed_cr.commit()
            with (
                db_connect(self.env.cr.dbname).cursor() as first_cr,
                db_connect(self.env.cr.dbname).cursor() as stale_cr,
            ):
                first = api.Environment(first_cr, SUPERUSER_ID, context)
                stale = api.Environment(stale_cr, SUPERUSER_ID, context)
                stale_cr.execute("SELECT count(*) FROM resource_relation")
                first["resource.relation"].create(
                    {
                        "parent_id": a,
                        "member_id": b,
                        "relation_type": "depends_on",
                        "date_start": False,
                    }
                )
                first_cr.commit()
                with self.assertRaises(SerializationFailure):
                    stale["resource.relation"].create(
                        {
                            "parent_id": c,
                            "member_id": d,
                            "relation_type": "depends_on",
                            "date_start": False,
                        }
                    )
                stale_cr.rollback()
                stale = api.Environment(stale_cr, SUPERUSER_ID, context)
                with self.assertRaises(ValidationError), stale_cr.savepoint():
                    stale["resource.relation"].create(
                        {
                            "parent_id": c,
                            "member_id": d,
                            "relation_type": "depends_on",
                            "date_start": False,
                        }
                    )
        finally:
            if ids:
                with db_connect(self.env.cr.dbname).cursor() as cleanup_cr:
                    cleanup = api.Environment(cleanup_cr, SUPERUSER_ID, context)
                    cleanup["resource.relation"].with_context(active_test=False).search(
                        [
                            "|",
                            ("parent_id", "in", ids),
                            ("member_id", "in", ids),
                        ]
                    ).unlink()
                    cleanup["resource.resource"].browse(ids).unlink()
                    cleanup_cr.commit()

    def test_archived_reservation_preserves_its_resource_identity(self):
        claim = self.env["resource.reservation"].create(
            {
                "name": "Historical booking",
                "resource_id": self.parent.id,
                "date_start": self.start,
                "date_end": self.end,
                "active": False,
            }
        )
        with self.assertRaises(UserError), self.cr.savepoint():
            self.parent.unlink()
        self.assertEqual(claim.resource_id, self.parent)
        with (
            self.assertRaises(RestrictViolation),
            self.cr.savepoint(),
            mute_logger("odoo.db.cursor"),
        ):
            self.cr.execute(
                "DELETE FROM resource_resource WHERE id = %s", [self.parent.id]
            )

    def test_composition_history_reports_that_archiving_is_required(self):
        relation = self._relation(date_end=self.end, active=False)
        with self.assertRaises(UserError), self.cr.savepoint():
            self.member.unlink()
        self.assertEqual(relation.member_id, self.member)

    def test_resource_without_operational_history_can_be_deleted(self):
        self.other.unlink()
        self.assertFalse(self.other.exists())
