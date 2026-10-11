from contextlib import suppress

from odoo.tests import counting_statements, tagged

from odoo.addons.mail.models.mail_followers import AUTO_SUBSCRIBE_QUEUE
from odoo.addons.mail.tests.common import MailCommon, mail_new_test_user


class AutoSubscribeCase(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._create_portal_user()
        cls.user_assignee = mail_new_test_user(
            cls.env,
            login="assignee",
            groups="base.group_user",
            name="Assignee",
            email="assignee@test.example.com",
            notification_type="inbox",
        )
        cls.partner_assignee = cls.user_assignee.partner_id
        cls.container = (
            cls.env["mail.test.container"]
            .with_context(mail_create_nosubscribe=True)
            .create({"name": "Container"})
        )
        cls.container.message_subscribe(
            cls.partner_portal.ids,
            subtype_ids=[cls.env.ref("test_mail.st_mail_test_container_child_full").id],
        )
        cls.Ticket = (
            cls.env["mail.test.ticket"]
            .with_user(cls.user_admin)
            .with_context(mail_create_nosubscribe=True, mail_create_nolog=True)
        )
        cls.tickets = cls.Ticket.create([{"name": f"Ticket {i}"} for i in range(3)])

    def setUp(self):
        super().setUp()
        self.flush_tracking()

    def _get_pending_ids(self):
        return {
            id_
            for _model, id_ in self.env.cr.precommit.data.get(AUTO_SUBSCRIBE_QUEUE)
            or ()
        }

    def _assign(self, records, user=None):
        records.write({"user_id": (user or self.user_assignee).id})
        self.assertLessEqual(
            set(records.ids),
            self._get_pending_ids(),
            "the write leaves its auto-subscription for later",
        )

    def _get_assignments(self, records):
        return (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", records._name),
                    ("res_id", "in", records.ids),
                    ("message_type", "=", "user_notification"),
                ],
                order="id",
            )
        )

    def _get_follower_rows(self, records, partner):
        return (
            self.env["mail.followers"]
            .sudo()
            .search_count(
                [
                    ("res_model", "=", records._name),
                    ("res_id", "in", records.ids),
                    ("partner_id", "=", partner.id),
                ]
            )
        )


@tagged("mail_followers", "post_install", "-at_install")
class TestAutoSubscribeReadPaths(AutoSubscribeCase):
    def test_a_write_that_can_subscribe_nobody_queues_nothing(self):
        ticket = self.tickets[0]
        followers = ticket.message_partner_ids
        ticket.write({"name": "Renamed"})
        self.assertFalse(self._get_pending_ids())
        with self.assertQueryCount(0):
            self.assertEqual(ticket.message_partner_ids, followers)
        ticket.write({"container_id": self.container.id})
        self.assertEqual(self._get_pending_ids(), {ticket.id})

    def test_message_partner_ids_sees_a_pending_assignment_over_a_warm_cache(self):
        ticket = self.tickets[0]
        self.assertNotIn(self.partner_assignee, ticket.message_partner_ids)
        self._assign(ticket)
        self.assertIn(self.partner_assignee, ticket.message_partner_ids)
        self.assertNotIn(ticket.id, self._get_pending_ids())

    def test_message_follower_ids_sees_a_pending_assignment(self):
        ticket = self.tickets[0]
        self._assign(ticket)
        self.assertIn(self.partner_assignee, ticket.message_follower_ids.partner_id)

    def test_message_is_follower_sees_a_pending_assignment(self):
        ticket = self.tickets[0]
        self.assertFalse(ticket.with_user(self.user_assignee).message_is_follower)
        self._assign(ticket)
        self.assertTrue(ticket.with_user(self.user_assignee).message_is_follower)

    def test_searches_on_followers_see_a_pending_assignment(self):
        ticket = self.tickets[0]
        self._assign(ticket)
        self.assertEqual(
            self.Ticket.search(
                [
                    ("id", "in", self.tickets.ids),
                    ("message_partner_ids", "in", self.partner_assignee.ids),
                ]
            ),
            ticket,
        )
        self.assertEqual(
            self.Ticket.with_user(self.user_assignee).search(
                [("id", "in", self.tickets.ids), ("message_is_follower", "=", True)]
            ),
            ticket,
        )
        self.assertEqual(self._get_follower_rows(ticket, self.partner_assignee), 1)

    def test_followers_store_sees_a_pending_assignment(self):
        ticket = self.tickets[0]
        self._assign(ticket)
        followers = ticket.message_get_followers()["mail.followers"]
        self.assertIn(
            self.partner_assignee.id, [follower["partner_id"] for follower in followers]
        )

    def test_unsubscribe_after_a_pending_assignment_removes_it(self):
        ticket = self.tickets[0]
        self._assign(ticket)
        ticket.message_unsubscribe(self.partner_assignee.ids)
        self.flush_tracking()
        self.assertEqual(self._get_follower_rows(ticket, self.partner_assignee), 0)

    def test_subscribe_after_a_pending_assignment_keeps_its_subtypes(self):
        ticket = self.tickets[0]
        note = self.env.ref("mail.mt_note")
        self._assign(ticket)
        ticket.message_subscribe(self.partner_assignee.ids, subtype_ids=note.ids)
        self.flush_tracking()
        follower = ticket.message_follower_ids.filtered(
            lambda f: f.partner_id == self.partner_assignee
        )
        self.assertEqual(follower.subtype_ids, note)

    def test_access_by_following_sees_a_pending_parent_subscription(self):
        ticket = self.tickets[0]
        self.assertFalse(
            self.Ticket.with_user(self.user_portal).search([("id", "=", ticket.id)])
        )
        ticket.container_id = self.container
        self.assertIn(ticket.id, self._get_pending_ids())
        ticket.with_user(self.user_portal).check_access("read")
        self.assertEqual(
            self.Ticket.with_user(self.user_portal).search([("id", "=", ticket.id)]),
            ticket,
        )

    def test_a_post_notifies_a_pending_assignee_after_the_assignment(self):
        ticket = self.tickets[0]
        self._assign(ticket)
        message = ticket.message_post(
            body="Hello", message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        self.assertIn(self.partner_assignee, message.notification_ids.res_partner_id)
        assignment = self._get_assignments(ticket)
        self.assertEqual(len(assignment), 1)
        self.assertLess(assignment.id, message.id)


@tagged("mail_followers", "post_install", "-at_install")
class TestAutoSubscribeOrdering(AutoSubscribeCase):
    def test_assignment_is_notified_before_tracking_is_posted(self):
        ticket = self.tickets[0]
        self._assign(ticket)
        self.flush_tracking()
        assignment = self._get_assignments(ticket)
        tracking = ticket.message_ids.filtered("tracking_value_ids")
        self.assertEqual(len(assignment), 1)
        self.assertEqual(len(tracking), 1)
        self.assertLess(assignment.id, tracking.id)
        self.assertEqual(
            assignment.notification_ids.res_partner_id, self.partner_assignee
        )

    def test_a_rewrite_notifies_with_the_values_of_the_assignment(self):
        ticket = self.tickets[0]
        self._assign(ticket)
        ticket.name = "Renamed"
        self.assertEqual(len(self._get_assignments(ticket)), 1)
        self.flush_tracking()
        self.assertIn("Ticket 0", self._get_assignments(ticket).subject)

    def test_each_reassignment_subscribes_and_notifies(self):
        ticket = self.tickets[0]
        self._assign(ticket)
        self._assign(ticket, self.user_employee)
        self.flush_tracking()
        assignments = self._get_assignments(ticket)
        self.assertEqual(
            assignments.notification_ids.res_partner_id,
            self.partner_assignee | self.partner_employee,
        )
        self.assertEqual(
            assignments[0].notification_ids.res_partner_id, self.partner_assignee
        )
        self.assertLessEqual(
            self.partner_assignee | self.partner_employee, ticket.message_partner_ids
        )

    def test_a_loop_of_assignments_notifies_each_record_once(self):
        for ticket in self.tickets:
            self._assign(ticket)
        self.flush_tracking()
        for ticket in self.tickets:
            self.assertEqual(len(self._get_assignments(ticket)), 1)
            self.assertIn(self.partner_assignee, ticket.message_partner_ids)

    def test_flushing_dirty_followers_leaves_the_queue_to_the_commit(self):
        ticket = self.tickets[0]
        ticket.message_subscribe(self.partner_employee.ids)
        follower = ticket.message_follower_ids
        follower.write({"partner_id": self.partner_admin.id})
        self._assign(ticket)
        self.env.flush_all()
        self.assertIn(ticket.id, self._get_pending_ids())
        self.flush_tracking()
        self.assertEqual(len(self._get_assignments(ticket)), 1)

    def test_unlinking_a_pending_record_leaves_no_follower_nor_message(self):
        ticket = self.tickets[0]
        self._assign(ticket)
        ticket_id = ticket.id
        ticket.unlink()
        self.flush_tracking()
        self.assertFalse(
            self.env["mail.followers"]
            .sudo()
            .search(
                [("res_model", "=", "mail.test.ticket"), ("res_id", "=", ticket_id)]
            )
        )
        self.assertFalse(
            self.env["mail.message"]
            .sudo()
            .search([("model", "=", "mail.test.ticket"), ("res_id", "=", ticket_id)])
        )


@tagged("mail_followers", "post_install", "-at_install")
class TestAutoSubscribeSavepoint(AutoSubscribeCase):
    def test_an_assignment_rolled_back_neither_subscribes_nor_notifies(self):
        ticket = self.tickets[0]
        with self.assertRaises(ZeroDivisionError), self.env.cr.savepoint():
            self._assign(ticket)
            _ = 1 / 0
        self.assertFalse(self._get_pending_ids())
        self.flush_tracking()
        self.env.invalidate_all()
        self.assertEqual(self._get_follower_rows(ticket, self.partner_assignee), 0)
        self.assertFalse(self._get_assignments(ticket))

    def test_a_rollback_keeps_what_was_pending_before_the_savepoint(self):
        kept, dropped = self.tickets[:2]
        self._assign(kept)
        with suppress(ZeroDivisionError), self.env.cr.savepoint(flush=False):
            self._assign(dropped)
            _ = 1 / 0
        self.assertEqual(self._get_pending_ids(), {kept.id})
        self.flush_tracking()
        self.env.invalidate_all()
        self.assertEqual(self._get_follower_rows(kept, self.partner_assignee), 1)
        self.assertEqual(len(self._get_assignments(kept)), 1)
        self.assertEqual(self._get_follower_rows(dropped, self.partner_assignee), 0)
        self.assertFalse(self._get_assignments(dropped))

    def test_a_finalization_rolled_back_runs_again_at_commit(self):
        ticket = self.tickets[0]
        self._assign(ticket)
        with suppress(ZeroDivisionError), self.env.cr.savepoint(flush=False):
            self.assertIn(self.partner_assignee, ticket.message_partner_ids)
            self.assertEqual(len(self._get_assignments(ticket)), 1)
            _ = 1 / 0
        self.env.invalidate_all()
        self.assertEqual(self._get_pending_ids(), {ticket.id})
        self.assertEqual(self._get_follower_rows(ticket, self.partner_assignee), 1)
        self.flush_tracking()
        self.env.invalidate_all()
        self.assertEqual(self._get_follower_rows(ticket, self.partner_assignee), 1)
        self.assertEqual(len(self._get_assignments(ticket)), 1)


@tagged("mail_followers", "mail_performance", "post_install", "-at_install")
class TestAutoSubscribeScaling(AutoSubscribeCase):
    def test_assigning_record_by_record_costs_what_one_batch_costs(self):
        self._assign(self.Ticket.create([{"name": "Warmup"}]))
        self.flush_tracking()
        counts = {}
        for size in (5, 25):
            tickets = self.Ticket.create([{"name": f"T{i}"} for i in range(size)])
            self.env.invalidate_all()
            self.flush_tracking()
            with counting_statements(self.env.cr) as statements:
                for ticket in tickets:
                    ticket.user_id = self.user_assignee
                self.flush_tracking()
                counts[size] = statements.count
            for ticket in tickets:
                self.assertEqual(len(self._get_assignments(ticket)), 1)
            self.assertEqual(
                self._get_follower_rows(tickets, self.partner_assignee), size
            )
        slope = (counts[25] - counts[5]) / 20
        self.assertLess(
            slope,
            2,
            "assigning costs %.2f statements per record (%s for 5, %s for 25): "
            "each write subscribes and notifies on its own again"
            % (slope, counts[5], counts[25]),
        )
