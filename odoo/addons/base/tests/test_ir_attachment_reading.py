from datetime import timedelta
from unittest.mock import patch

import psycopg.errors

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.db import db_connect
from odoo.exceptions import AccessError
from odoo.fields import Datetime
from odoo.libs.documents import (
    CUES,
    METERED,
    TEXT,
    BaseReader,
    Cue,
    register_reader,
    unregister_reader,
)
from odoo.tests.common import (
    BaseCase,
    TransactionCase,
    get_db_name,
    new_test_user,
    tagged,
)

MIMETYPE = "application/x-reading-test"


class _Listens(BaseReader):
    name = "reading_test_listens"
    mimetypes = frozenset({MIMETYPE})
    yields = (CUES,)
    cost = METERED

    def __init__(self):
        self.reads = 0
        self.error = None
        self.cues = [Cue(0.0, 1.5, "the invoice went out", "SPEAKER_0")]

    def read(self, document):
        self.reads += 1
        if self.error:
            raise self.error
        return list(self.cues)


@tagged("post_install", "-at_install")
class TestAttachmentReading(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.listens = register_reader(_Listens())
        cls.addClassCleanup(unregister_reader, cls.listens)

    def setUp(self):
        super().setUp()
        self.listens.reads = 0
        self.listens.error = None
        self.listens.cues = [Cue(0.0, 1.5, "the invoice went out", "SPEAKER_0")]

    def _file(self, raw=b"recorded bytes", **values):
        return self.env["ir.attachment"].create(
            {"name": "call.bin", "raw": raw, "mimetype": MIMETYPE, **values}
        )

    def test_a_reading_is_kept_and_not_read_twice(self):
        attachment = self._file()
        cues = attachment._read(CUES)
        self.assertEqual([cue.text for cue in cues], ["the invoice went out"])
        reading = attachment._reading(CUES)
        self.assertEqual(reading.state, "done")
        self.assertEqual(reading.read_by, "reading_test_listens")
        self.assertEqual(reading.checksum, attachment.checksum)
        document = attachment._as_document(read_up_to=METERED)
        self.assertEqual(document.cues[0].speaker, "SPEAKER_0")
        self.assertEqual(document.read_by(CUES), "reading_test_listens")
        self.assertEqual(self.listens.reads, 1, "the kept reading answered")

    def test_what_is_read_becomes_searchable(self):
        attachment = self._file()
        attachment._read(CUES)
        self.assertIn("invoice went out", attachment.index_content)

    def test_a_failure_keeps_its_reason(self):
        self.listens.error = RuntimeError("vendor down")
        attachment = self._file()
        self.assertFalse(attachment._read(CUES))
        reading = attachment._reading(CUES)
        self.assertEqual(reading.state, "failed")
        self.assertEqual(reading.error, "vendor down")

    def test_nothing_said_is_a_reading_too(self):
        self.listens.cues = []
        attachment = self._file()
        self.assertEqual(attachment._read(CUES), [])
        self.assertEqual(attachment._reading(CUES).state, "done")

    def test_new_bytes_are_read_again(self):
        attachment = self._file()
        attachment._read(CUES)
        attachment.write({"raw": b"other bytes", "mimetype": MIMETYPE})
        self.assertFalse(attachment._reading(CUES), "the reading was of old bytes")
        attachment._read(CUES)
        self.assertEqual(self.listens.reads, 2)

    def test_released_bytes_keep_what_they_said(self):
        attachment = self._file()
        attachment._read(CUES)
        attachment._release_content()
        self.assertTrue(attachment.content_released_at)
        self.assertEqual(attachment._reading(CUES).state, "done")

    def test_a_copy_shares_the_reading(self):
        attachment = self._file()
        attachment._read(CUES)
        copied = attachment.copy()
        self.assertEqual(copied._reading(CUES).state, "done")
        self.assertEqual(
            copied._as_document(read_up_to=METERED).cues[0].text, "the invoice went out"
        )
        self.assertEqual(self.listens.reads, 1)

    def test_a_file_says_it_was_read_and_its_copy_too(self):
        attachment = self._file()
        self.assertFalse(attachment.has_readings)
        attachment._read(CUES)
        self.assertTrue(attachment.has_readings)
        self.assertTrue(attachment.copy().has_readings)

    def test_a_kept_reading_answers_without_loading_the_file(self):
        attachment = self._file()
        attachment._read(CUES)
        IrAttachment = type(self.env["ir.attachment"])
        with patch.object(
            IrAttachment, "_get_content", side_effect=AssertionError("loaded")
        ):
            document = attachment._as_document(read_up_to=METERED)
            self.assertEqual(document.cues[0].text, "the invoice went out")
        self.assertEqual(self.listens.reads, 1)

    def test_a_copy_of_a_file_never_read_looks_for_no_reading(self):
        attachment = self._file()
        Reading = type(self.env["ir.attachment.reading"])
        with patch.object(Reading, "search", side_effect=AssertionError("searched")):
            copied = attachment.copy()
        self.assertFalse(copied.has_readings)
        self.assertFalse(copied.reading_ids)

    def test_a_reading_made_elsewhere_is_stored_as_given(self):
        attachment = self._file()
        attachment._store_reading(TEXT, "typed by hand", read_by="migration")
        self.assertEqual(attachment._as_document().text, "typed by hand")
        self.assertIn("typed by hand", attachment.index_content)

    def test_a_reading_outlives_a_content_write_still_pending(self):
        attachment = self.env["ir.attachment"].create(
            {"name": "note.txt", "raw": b"first raw words", "mimetype": "text/plain"}
        )
        attachment._read_later(TEXT)
        attachment.write({"raw": b"second raw words"})
        attachment._store_reading(TEXT, "words worth finding", read_by="test")
        self.env.flush_all()
        attachment.invalidate_recordset(["index_content"])
        self.assertEqual(attachment.index_content, "words worth finding")

    def test_history_is_kept_without_telling_anyone(self):
        attachment = self._file()
        told = []
        with patch.object(
            type(attachment), "_on_read", lambda self, *args: told.append(args)
        ):
            attachment._store_reading(
                TEXT, "moved", read_by="migration", announce=False
            )
        self.assertFalse(told)
        self.assertIn("moved", attachment.index_content)

    def test_reading_later_queues_one_job(self):
        attachment = self._file()
        attachment._read_later(CUES)
        attachment._read_later(CUES)
        self.assertEqual(attachment._reading(CUES).state, "queued")
        jobs = (
            self.env["ir.job"]
            .sudo()
            .search([("identity_key", "=", f"reading.{CUES}.{attachment.id}")])
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(self.listens.reads, 0)

    def test_asking_again_without_a_date_reads_now(self):
        attachment = self._file()
        attachment._read_later(CUES, eta=Datetime.now() + timedelta(hours=1))
        job = (
            self.env["ir.job"]
            .sudo()
            .search([("identity_key", "=", f"reading.{CUES}.{attachment.id}")])
        )
        self.assertEqual(job.state, "scheduled")
        attachment._read_later(CUES)
        job.invalidate_recordset()
        self.assertEqual(job.state, "pending")
        self.assertFalse(job.eta)

    def test_an_interrupted_reading_is_released(self):
        attachment = self._file()
        reading = attachment._reading_row(CUES)
        reading.state = "running"
        reading.flush_recordset()
        self.env.cr.execute(
            "UPDATE ir_attachment_reading SET write_date = %s WHERE id = %s",
            (Datetime.now() - timedelta(days=1), reading.id),
        )
        reading.invalidate_recordset()
        self.env["ir.attachment.reading"]._gc_interrupted_readings()
        self.assertEqual(reading.state, "failed")

    def test_a_reading_is_only_seen_by_who_sees_the_file(self):
        outsider = new_test_user(self.env, login="reading_outsider")
        private = self._file().with_user(SUPERUSER_ID)
        private._read(CUES)
        reading = private._reading(CUES)
        Reading = self.env["ir.attachment.reading"].with_user(outsider)
        self.assertFalse(Reading.search([("id", "=", reading.id)]))
        with self.assertRaises(AccessError):
            Reading.browse(reading.id).read(["value"])
        own = (
            self.env["ir.attachment"]
            .with_user(outsider)
            .create({"name": "own.bin", "raw": b"mine", "mimetype": MIMETYPE})
        )
        own.sudo()._read(CUES)
        self.assertTrue(Reading.search([("attachment_id", "=", own.id)]))


@tagged("post_install", "-at_install")
class TestReadingRowRace(BaseCase):
    def test_a_row_another_transaction_created_is_a_retry_not_nothing(self):
        dbname = get_db_name()
        with db_connect(dbname).cursor() as setup_cr:
            attachment_id = (
                api.Environment(setup_cr, SUPERUSER_ID, {})["ir.attachment"]
                .create({"name": "raced.bin", "raw": b"raced", "mimetype": MIMETYPE})
                .id
            )
            setup_cr.commit()

        def cleanup():
            with db_connect(dbname).cursor() as cr:
                api.Environment(cr, SUPERUSER_ID, {})["ir.attachment"].browse(
                    attachment_id
                ).unlink()
                cr.commit()

        self.addCleanup(cleanup)
        with (
            db_connect(dbname).cursor() as first_cr,
            db_connect(dbname).cursor() as second_cr,
        ):
            first = api.Environment(first_cr, SUPERUSER_ID, {})["ir.attachment"]
            second = api.Environment(second_cr, SUPERUSER_ID, {})["ir.attachment"]
            second_cr.execute("SELECT 1")
            first.browse(attachment_id)._reading_row(TEXT)
            first_cr.commit()
            with self.assertRaises(psycopg.errors.SerializationFailure):
                second.browse(attachment_id)._store_reading(TEXT, "lost words")
            second_cr.rollback()
