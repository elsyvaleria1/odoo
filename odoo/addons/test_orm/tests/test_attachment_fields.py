import base64

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools import SQL

PDF = base64.b64encode(b"%PDF-1.4 probe")


class TestRequiredAttachment(TransactionCase):
    def _files(self, records):
        return self.env["ir.attachment"].search(
            [
                ("res_model", "=", records._name),
                ("res_field", "=", "document"),
                ("res_id", "in", records.ids),
            ]
        )

    def test_create_with_the_key_omitted_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "document"):
            self.env["test_orm.required_attachment"].create({"name": "no file"})

    def test_create_with_false_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env["test_orm.required_attachment"].create(
                {"name": "no file", "document": False}
            )

    def test_a_batch_is_refused_when_one_record_lacks_the_file(self):
        with self.assertRaises(ValidationError):
            self.env["test_orm.required_attachment"].create(
                [{"name": "a", "document": PDF}, {"name": "b"}]
            )

    def test_create_with_a_file_stores_it(self):
        record = self.env["test_orm.required_attachment"].create(
            {"name": "file", "document": PDF}
        )
        self.assertEqual(len(self._files(record)), 1)

    def test_clearing_the_file_is_refused(self):
        record = self.env["test_orm.required_attachment"].create(
            {"name": "file", "document": PDF}
        )
        with self.assertRaises(ValidationError):
            record.write({"document": False})

    def test_writing_another_field_does_not_check_the_file(self):
        record = self.env["test_orm.required_attachment"].create(
            {"name": "file", "document": PDF}
        )
        record.write({"name": "renamed"})
        self.assertEqual(record.name, "renamed")


class TestNewStoredAttachmentBackfill(TransactionCase):
    def _thumbnails(self, records, field_name):
        return {
            attachment.res_id: attachment.datas
            for attachment in self.env["ir.attachment"].search(
                [
                    ("res_model", "=", records._name),
                    ("res_field", "=", field_name),
                    ("res_id", "in", records.ids),
                ]
            )
        }

    def test_a_field_the_previous_load_did_not_store_is_computed(self):
        Model = self.env["test_orm.computed_attachment"]
        records = Model.create([{"name": "one"}, {"name": "two"}])
        self.env.flush_all()
        # the state an upgrade that adds the field starts from: rows, no files,
        # and no stored reflection of the field
        self._thumbnails_of(records).unlink()
        self.env.cr.execute(
            SQL(
                "UPDATE ir_model_fields SET store = false"
                " WHERE model = %s AND name = 'thumbnail'",
                Model._name,
            )
        )
        self.env.invalidate_all()

        self.registry.init_models(self.env.cr, [Model._name], {"module": "test_orm"})
        self.env.flush_all()

        self.assertEqual(
            self._thumbnails(records, "thumbnail"),
            {
                records[0].id: base64.b64encode(b"one"),
                records[1].id: base64.b64encode(b"two"),
            },
        )

    def test_a_field_the_previous_load_stored_is_left_alone(self):
        Model = self.env["test_orm.computed_attachment"]
        records = Model.create([{"name": "one"}])
        self.env.flush_all()
        self._thumbnails_of(records).unlink()
        self.env.invalidate_all()

        self.registry.init_models(self.env.cr, [Model._name], {"module": "test_orm"})
        self.env.flush_all()

        self.assertEqual(self._thumbnails(records, "thumbnail"), {})

    def test_a_new_manual_field_is_computed_for_existing_rows(self):
        records = self.env["test_orm.computed_attachment"].create(
            [{"name": "one"}, {"name": "two"}]
        )
        self.env["ir.model.fields"].create(
            {
                "name": "x_file",
                "model_id": self.env.ref(
                    "test_orm.model_test_orm_computed_attachment"
                ).id,
                "state": "manual",
                "field_description": "A computed file",
                "ttype": "binary",
                "store": True,
                "depends": "name",
                "compute": "for r in self: r['x_file'] = 'cHJvYmU='",
            }
        )
        self.env.flush_all()

        self.assertEqual(
            self._thumbnails(records, "x_file"),
            {records[0].id: b"cHJvYmU=", records[1].id: b"cHJvYmU="},
        )

    def _thumbnails_of(self, records):
        return self.env["ir.attachment"].search(
            [
                ("res_model", "=", records._name),
                ("res_field", "=", "thumbnail"),
                ("res_id", "in", records.ids),
            ]
        )
