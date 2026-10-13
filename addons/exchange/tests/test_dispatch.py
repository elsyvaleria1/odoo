import threading
import uuid

import psycopg
from psycopg.errors import LockNotAvailable, SerializationFailure

from odoo.modules.module import get_module_path, load_script
from odoo.service.transaction import retrying
from odoo.tests.common import tagged
from odoo.tools import SQL, mute_logger

from .common import ExchangeCase
from odoo.addons.base.models.ir_job import CLAIMED_COLUMNS
from odoo.addons.exchange.models import exchange_transmission
from odoo.addons.exchange.tools import NotDelivered, Verdict

_LOGGER = "odoo.addons.exchange.models.exchange_transmission"


@tagged("post_install", "-at_install")
class TestExchangeDispatchRace(ExchangeCase):
    def _commit_queued(self):
        with self.registry.cursor() as cr:
            env = self.env(cr=cr)
            endpoint = env["integration.service"].create(
                {
                    "name": "Race Counterparty",
                    "code": f"race_{uuid.uuid4().hex}",
                    "category": "tax",
                    "endpoint_url": "https://race.example.com",
                    "environment": "test",
                },
            )
            channel = env["exchange.channel"].create(
                {"endpoint_id": endpoint.id, "protocol": "demo"},
            )
            subject = env["res.partner"].create({"name": "Race Co"})
            transmission = subject.with_context(
                demo_channel=channel
            )._add_transmission()
            ids = endpoint.id, channel.id, subject.id, transmission.id
        self.addCleanup(self._drop_committed, *ids)
        return ids

    def _drop_committed(self, endpoint_id, channel_id, subject_id, transmission_id):
        with self.leave_registry_test_mode(), self.registry.cursor() as cr:
            env = self.env(cr=cr)
            transmissions = env["exchange.transmission"].search(
                [("channel_id", "=", channel_id)]
            )
            cr.execute(
                "DELETE FROM ir_job WHERE identity_key = ANY(%s)",
                [
                    [
                        f"exchange.send:{channel_id}",
                        *(
                            f"exchange.react:{transmission.id}:{event}"
                            for transmission in transmissions
                            for event in ("settled", "unresolved")
                        ),
                    ]
                ],
            )
            cr.execute(
                "DELETE FROM exchange_transmission_dispatch WHERE ask_identity LIKE %s",
                [f"res.partner,{subject_id}|%"],
            )
            transmissions.unlink()
            env["integration.service"].browse(endpoint_id).unlink()
            env["res.partner"].browse(subject_id).unlink()

    def _send_new(self, cr, channel_id, subject_id):
        env = self.env(cr=cr)
        env["res.partner"].browse(subject_id).with_context(
            demo_channel=env["exchange.channel"].browse(channel_id)
        )._add_transmission()._send()

    def _read_channel(self, channel_id, *fnames):
        with self.registry.cursor() as cr:
            transmissions = self.env(cr=cr)["exchange.transmission"].search(
                [("channel_id", "=", channel_id)], order="id"
            )
            return [
                [transmission[fname] for fname in fnames]
                for transmission in transmissions
            ]

    def _record_sends(self, gate=None):
        sent = []

        def send_message(protocol, transmission, document):
            sent.append(transmission.id)
            if gate:
                gate()
            return Verdict(state="accepted", reference=f"RACE-{len(sent)}")

        self.patch(
            type(self.env["exchange.protocol.demo"]), "_send_message", send_message
        )
        return sent

    def _fail_once_after_sending(self, error):
        model = self.registry["exchange.transmission"]
        send_many = model._send_many
        pending = [error]

        def fail_after_sending(transmissions):
            send_many(transmissions)
            if pending:
                raise pending.pop()

        self.patch(model, "_send_many", fail_after_sending)

    def _start_send_job(self, channel_id):
        with self.registry.cursor() as cr:
            cr.execute(
                SQL(
                    "UPDATE ir_job SET state = 'started',"
                    " started_at = (now() AT TIME ZONE 'UTC')"
                    " WHERE identity_key = %s AND state = 'pending' RETURNING %s",
                    f"exchange.send:{channel_id}",
                    CLAIMED_COLUMNS,
                )
            )
            names = [column.name for column in cr.description]
            return dict(zip(names, cr.fetchone(), strict=True))

    def _read(self, transmission_id, *fnames):
        with self.registry.cursor() as cr:
            transmission = self.env(cr=cr)["exchange.transmission"].browse(
                transmission_id
            )
            return [transmission[fname] for fname in fnames]

    def _send_queued(self, cr, channel_id):
        self.env(cr=cr)["exchange.channel"].browse(channel_id)._job_send_queued()

    def test_a_send_job_replayed_after_its_call_does_not_send_again(self):
        with self.leave_registry_test_mode():
            _endpoint, channel_id, _subject, transmission_id = self._commit_queued()
            sent = self._record_sends()
            self._fail_once_after_sending(
                SerializationFailure("could not serialize access")
            )
            job = self._start_send_job(channel_id)

            with self.registry.cursor() as cr, mute_logger("odoo.addons.base"):
                error = type(self.env["ir.job"])._run_with_concurrency_replay(
                    self.registry, cr, job
                )

            self.assertIsNone(error)
            self.assertEqual(
                sent,
                [transmission_id],
                "the replay rolled back the record of a call the counterparty "
                "already answered, and handed it the document a second time",
            )
            self.assertEqual(self._read(transmission_id, "state"), ["queued"])

            with self.registry.cursor() as cr, mute_logger(_LOGGER):
                self.env(cr=cr)["exchange.transmission"]._cron_send_queued()

            state, message = self._read(transmission_id, "state", "message")
            self.assertEqual(
                state,
                "expired",
                "the demo counterparty can neither be asked nor safely sent to "
                "again, so the lost answer goes to the document's owner",
            )
            self.assertIn("never recorded", message)
            self.assertEqual(sent, [transmission_id])

    def test_a_sender_on_an_older_snapshot_does_not_resend_a_dispatch_that_died(self):
        with self.leave_registry_test_mode():
            _endpoint, channel_id, _subject, transmission_id = self._commit_queued()
            sent = self._record_sends()
            self._fail_once_after_sending(RuntimeError("worker killed"))

            with self.registry.cursor() as late:
                late.execute("SELECT 1")
                with self.registry.cursor() as cr:
                    with self.assertRaises(RuntimeError):
                        self._send_queued(cr, channel_id)
                    cr.rollback()
                self._send_queued(late, channel_id)

            self.assertEqual(
                sent,
                [transmission_id],
                "a sender whose snapshot predates the dead dispatch must still "
                "find it claimed",
            )
            self.assertEqual(self._read(transmission_id, "state"), ["queued"])

    def test_a_dispatch_still_in_flight_is_left_to_its_sender(self):
        with self.leave_registry_test_mode():
            _endpoint, channel_id, _subject, transmission_id = self._commit_queued()
            calling, answer = threading.Event(), threading.Event()

            def hold_the_call():
                calling.set()
                answer.wait(30)

            sent = self._record_sends(gate=hold_the_call)

            def dispatch():
                with self.registry.cursor() as cr:
                    self._send_queued(cr, channel_id)

            sender = threading.Thread(target=dispatch)
            sender.start()
            try:
                self.assertTrue(calling.wait(30))
                with self.registry.cursor() as cr:
                    self.env(cr=cr)["exchange.transmission"]._cron_send_queued()
                with self.registry.cursor() as cr:
                    self._send_queued(cr, channel_id)
            finally:
                answer.set()
                sender.join(60)

            self.assertEqual(sent, [transmission_id])
            self.assertEqual(
                self._read(transmission_id, "state", "reference"),
                ["accepted", "RACE-1"],
                "the sweep took a call still waiting for its answer for a lost one",
            )

    def test_a_request_replayed_after_sending_a_transmission_it_created_does_not_send_again(
        self,
    ):
        with self.leave_registry_test_mode():
            _endpoint, channel_id, subject_id, queued_id = self._commit_queued()
            sent = self._record_sends()
            failures = [SerializationFailure("could not serialize access")]

            with (
                self.registry.cursor() as cr,
                mute_logger("odoo.service.transaction", _LOGGER),
            ):

                def request():
                    self._send_new(cr, channel_id, subject_id)
                    if failures:
                        raise failures.pop()

                retrying(request, self.env(cr=cr))

            self.assertEqual(
                len(sent),
                1,
                "the replay created the transmission again and handed the "
                "counterparty the document a second time",
            )
            [[replayed_id, state, message]] = [
                row
                for row in self._read_channel(channel_id, "id", "state", "message")
                if row[0] != queued_id
            ]
            self.assertNotIn(replayed_id, sent)
            self.assertEqual(state, "expired")
            self.assertIn("never recorded", message)

    def test_a_document_sent_by_a_request_that_rolled_back_is_not_sent_by_the_next(
        self,
    ):
        with self.leave_registry_test_mode():
            _endpoint, channel_id, subject_id, queued_id = self._commit_queued()
            sent = self._record_sends()

            with self.registry.cursor() as cr:
                self._send_new(cr, channel_id, subject_id)
                cr.rollback()
            with self.registry.cursor() as cr, mute_logger(_LOGGER):
                self._send_new(cr, channel_id, subject_id)

            self.assertEqual(len(sent), 1)
            self.assertEqual(
                [
                    state
                    for transmission_id, state in self._read_channel(
                        channel_id, "id", "state"
                    )
                    if transmission_id != queued_id
                ],
                ["expired"],
            )

    def test_a_concurrency_failure_before_the_call_leaves_the_send_to_the_replay(
        self,
    ):
        with self.leave_registry_test_mode():
            _endpoint, channel_id, _subject, transmission_id = self._commit_queued()
            sent = self._record_sends()
            protocol = type(self.env["exchange.protocol.demo"])
            prepare_message = protocol._prepare_message
            failures = [SerializationFailure("could not serialize access")]

            def prepare_failing_once(protocol, transmission):
                if failures:
                    raise failures.pop()
                return prepare_message(protocol, transmission)

            self.patch(protocol, "_prepare_message", prepare_failing_once)
            job = self._start_send_job(channel_id)

            with self.registry.cursor() as cr, mute_logger("odoo.addons.base"):
                error = type(self.env["ir.job"])._run_with_concurrency_replay(
                    self.registry, cr, job
                )
            with self.registry.cursor() as cr:
                self.env(cr=cr)["exchange.transmission"]._cron_send_queued()

            self.assertIsNone(error)
            self.assertEqual(
                sent,
                [transmission_id],
                "the document was never handed off, yet its claim outlived the "
                "rollback and the replay took it for a lost answer",
            )
            self.assertEqual(
                self._read(transmission_id, "state", "reference"),
                ["accepted", "RACE-1"],
            )

    def test_a_document_that_never_left_is_sent_by_the_replay_of_its_job(self):
        with self.leave_registry_test_mode():
            _endpoint, channel_id, subject_id, _queued = self._commit_queued()
            with self.registry.cursor() as cr:
                env = self.env(cr=cr)
                env["res.partner"].browse(subject_id).with_context(
                    demo_channel=env["exchange.channel"].browse(channel_id)
                )._add_transmission()
            protocol = type(self.env["exchange.protocol.demo"])
            prepare_message = protocol._prepare_message
            attempts = []
            failures = [SerializationFailure("could not serialize access")]

            def send_message(protocol, transmission, document):
                attempts.append(transmission.id)
                if len(attempts) == 1:
                    raise NotDelivered("connection refused")
                return Verdict(state="accepted", reference=f"RACE-{len(attempts)}")

            def prepare_failing_after_a_refusal(protocol, transmission):
                if attempts and failures:
                    raise failures.pop()
                return prepare_message(protocol, transmission)

            self.patch(protocol, "_send_message", send_message)
            self.patch(protocol, "_prepare_message", prepare_failing_after_a_refusal)
            job = self._start_send_job(channel_id)

            with (
                self.registry.cursor() as cr,
                mute_logger("odoo.addons.base", _LOGGER),
            ):
                error = type(self.env["ir.job"])._run_with_concurrency_replay(
                    self.registry, cr, job
                )
            with self.registry.cursor() as cr, mute_logger(_LOGGER):
                self.env(cr=cr)["exchange.transmission"]._cron_send_queued()

            self.assertIsNone(error)
            self.assertEqual(
                attempts.count(attempts[0]),
                2,
                "the counterparty refused the first call, so the replay must "
                "make it again rather than take it for a lost answer",
            )
            self.assertEqual(
                self._read_channel(channel_id, "state"), [["accepted"], ["accepted"]]
            )

    def _cancel_lock_waits(self, after):
        stop = threading.Event()
        dbname = self.env.cr.dbname

        def cancel():
            if stop.wait(after):
                return
            with psycopg.connect(dbname=dbname, autocommit=True) as conn:
                conn.execute(
                    "SELECT pg_cancel_backend(pid) FROM pg_stat_activity"
                    " WHERE wait_event_type = 'Lock'"
                    " AND datname = current_database()"
                )

        watchdog = threading.Thread(target=cancel)
        watchdog.start()

        def stop_watching():
            stop.set()
            watchdog.join()

        self.addCleanup(stop_watching)

    def test_a_sender_holding_its_company_row_does_not_wait_on_its_own_claim(self):
        with self.leave_registry_test_mode():
            _endpoint, channel_id, _subject, transmission_id = self._commit_queued()
            with self.registry.cursor() as cr:
                company = self.env(cr=cr)["res.company"].create({"name": "Locked Co"})
                cr.execute(
                    "UPDATE exchange_transmission SET company_id = %s WHERE id = %s",
                    [company.id, transmission_id],
                )
                company_id = company.id
            self.addCleanup(self._drop_company, company_id, transmission_id)
            sent = self._record_sends()
            self.patch(exchange_transmission, "DISPATCH_LOCK_TIMEOUT", "200ms")
            self._cancel_lock_waits(after=10)

            raised = None
            with self.registry.cursor() as cr:
                cr.execute(
                    "SELECT id FROM res_company WHERE id = %s FOR UPDATE", [company_id]
                )
                try:
                    self._send_queued(cr, channel_id)
                except psycopg.Error as error:
                    raised = error
                cr.rollback()

            self.assertIsInstance(
                raised,
                LockNotAvailable,
                "the claim waited on the company row its own sender holds",
            )
            self.assertEqual(sent, [])

    def _drop_company(self, company_id, transmission_id):
        with self.leave_registry_test_mode(), self.registry.cursor() as cr:
            cr.execute(
                "UPDATE exchange_transmission SET company_id = %s WHERE id = %s",
                [self.env.company.id, transmission_id],
            )
            cr.execute("DELETE FROM res_company WHERE id = %s", [company_id])


@tagged("post_install", "-at_install")
class TestExchangeDispatch(ExchangeCase):
    def setUp(self):
        super().setUp()
        self.sent = []

        def send_message(protocol, transmission, document):
            self.sent.append(transmission.id)
            return self._accepted(f"SENT-{len(self.sent)}")

        self.patch(
            type(self.env["exchange.protocol.demo"]), "_send_message", send_message
        )

    def _lose_answer(self, transmission):
        self.env.flush_all()
        self.env.cr.execute(
            "INSERT INTO exchange_transmission_dispatch"
            " (transmission_id, company_id, generation, date_dispatched)"
            " VALUES (%s, %s, %s, now() AT TIME ZONE 'UTC' - interval '1 minute')",
            [
                transmission.id,
                transmission.company_id.id,
                transmission.dispatch_count + 1,
            ],
        )

    def _capable(self, reconcilable=False, idempotent=False):
        protocol = type(self.env["exchange.protocol.demo"])
        self.patch(protocol, "_is_reconcilable", reconcilable)
        self.patch(protocol, "_is_resend_idempotent", idempotent)

    def _sweep(self):
        self.env["exchange.transmission"]._cron_send_queued()
        self.env.invalidate_all()

    def _dispatch_rows(self, transmission):
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT generation FROM exchange_transmission_dispatch"
            " WHERE transmission_id = %s ORDER BY generation",
            [transmission.id],
        )
        return [generation for [generation] in self.env.cr.fetchall()]

    def test_a_send_counts_its_hand_off_and_leaves_nothing_in_flight(self):
        transmission = self._add_transmission()
        self.channel._job_send_queued()

        self.assertEqual(transmission.state, "accepted")
        self.assertEqual(transmission.dispatch_count, 1)
        self.assertEqual(self._dispatch_rows(transmission), [1])

        self._sweep()
        self.assertEqual(transmission.state, "accepted")
        self.assertEqual(
            self._dispatch_rows(transmission),
            [],
            "a hand-off whose answer is recorded is swept from the journal",
        )

    def test_a_hand_off_with_no_recorded_answer_is_not_sent_again(self):
        transmission = self._add_transmission()
        self._lose_answer(transmission)

        with self.assertLogs(_LOGGER, "INFO") as logs:
            self.channel._job_send_queued()
            transmission._send_many()

        self.assertEqual(self.sent, [])
        self.assertEqual(transmission.state, "queued")
        self.assertIn("no recorded answer", logs.output[0])

    def test_a_hand_off_another_sender_claimed_is_left_to_it(self):
        transmission = self._add_transmission()
        self._lose_answer(transmission)
        self.patch(
            type(self.env["exchange.transmission.dispatch"]),
            "_get_unanswered",
            lambda dispatches, transmission_ids=None: {},
        )

        with self.assertLogs(_LOGGER, "INFO") as logs:
            transmission._send_many()

        self.assertEqual(
            self.sent,
            [],
            "the journal, not the sender's own snapshot, decides who may call",
        )
        self.assertIn("another sender", logs.output[0])

    def test_the_sweep_reads_back_a_lost_answer_where_it_can(self):
        self._capable(reconcilable=True)
        transmission = self._add_transmission()
        self._lose_answer(transmission)

        self._sweep()

        self.assertEqual(transmission.state, "sent")
        self.assertEqual(transmission.dispatch_count, 1)
        self.assertTrue(transmission.date_sent)
        self.assertTrue(transmission.date_reconcile_deadline)
        self.assertIn("never recorded", transmission.message)
        self.assertIn("read back", transmission.message)
        self.assertEqual(self.sent, [])

    def test_the_sweep_sends_a_lost_answer_again_where_the_counterparty_deduplicates(
        self,
    ):
        self._capable(idempotent=True)
        transmission = self._add_transmission()
        self._lose_answer(transmission)

        self._sweep()

        self.assertEqual(transmission.state, "queued")
        self.assertEqual(transmission.retry_count, 1)
        self.assertEqual(transmission.dispatch_count, 1)
        self.assertIn("sent again", transmission.message)

        transmission.date_next_retry = "2000-01-01 00:00:00"
        self.channel._job_send_queued()
        self.assertEqual(self.sent, [transmission.id])
        self.assertEqual(transmission.state, "accepted")
        self.assertEqual(transmission.dispatch_count, 2)

    def test_the_sweep_hands_a_lost_answer_nothing_can_resolve_to_its_owner(self):
        unresolved = []
        self.patch(
            type(self.subject),
            "_on_transmission_unresolved",
            lambda subject, transmission: unresolved.append(transmission),
        )
        transmission = self._add_transmission()
        self._lose_answer(transmission)

        self._sweep()

        self.assertEqual(transmission.state, "expired")
        self.assertIn("never recorded", transmission.message)
        self.assertEqual(unresolved, [transmission])
        self.assertEqual(self._dispatch_rows(transmission), [])
        self.assertEqual(self.sent, [])

    def test_the_upgrade_lets_a_claim_outlive_its_transmission(self):
        transmission = self._add_transmission()
        self._lose_answer(transmission)
        cr = self.env.cr
        cr.execute(
            "ALTER TABLE exchange_transmission_dispatch"
            " ADD CONSTRAINT exchange_transmission_dispatch_transmission_id_fkey"
            " FOREIGN KEY (transmission_id) REFERENCES exchange_transmission(id)"
            " ON DELETE CASCADE"
        )
        cr.execute("ALTER TABLE exchange_transmission_dispatch DROP COLUMN company_id")
        script = load_script(
            f"{get_module_path('exchange')}/migrations/1.0.3/pre-migrate.py",
            "odoo.addons.exchange.migrations.pre_migrate_1_0_3",
        )

        script.migrate(cr, "19.0.1.0.2")

        cr.execute(
            "SELECT conname FROM pg_constraint"
            " WHERE conrelid = 'exchange_transmission_dispatch'::regclass"
            " AND contype = 'f'"
        )
        self.assertEqual(
            cr.fetchall(),
            [],
            "a claim taken before its transmission committed cannot reference it",
        )
        cr.execute(
            "SELECT company_id FROM exchange_transmission_dispatch"
            " WHERE transmission_id = %s",
            [transmission.id],
        )
        self.assertEqual(cr.fetchall(), [(transmission.company_id.id,)])

    def test_a_concurrency_failure_while_recording_reruns_the_send(self):
        transmission = self._add_transmission()

        def apply(transmission, verdict):
            raise SerializationFailure("could not serialize access")

        self.patch(type(transmission), "_apply", apply)

        with self.assertRaises(SerializationFailure):
            transmission._send_many()
