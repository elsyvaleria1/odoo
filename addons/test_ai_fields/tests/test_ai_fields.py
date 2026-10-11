import base64
import copy
import json
from unittest.mock import patch

from odoo import Command, fields
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase, tagged
from odoo.tools import SQL

from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.ai_fields.tools import UnresolvedQuery
from odoo.addons.base.tests.test_ir_cron import CronMixinCase


@tagged("post_install", "-at_install")
class TestAiFieldsCrons(TransactionCase, CronMixinCase):
    def test_ai_fields_cron_trigger(self):
        ai_field_cron_id = self.env.ref("ai_fields.ir_cron_fill_ai_fields").id
        with self.capture_triggers(ai_field_cron_id) as capt:
            self.env["test.ai.fields.no.ai"].create({"name": "Record"})
            self.assertFalse(len(capt.records))

        values = {
            "name": "x_ai_char",
            "model_id": self.env["ir.model"]._get("test.ai.fields.no.ai").id,
            "ttype": "char",
        }
        values_ai = {
            "ai": True,
            "system_prompt": "System Prompt {{object.name}}",
        }

        with self.capture_triggers(ai_field_cron_id) as capt:
            self.env["ir.model.fields"].create(values | values_ai)
            self.assertTrue(len(capt.records))

        with self.capture_triggers(ai_field_cron_id) as capt:
            field = self.env["ir.model.fields"].create(values | {"name": "x_ai_char_2"})
            self.assertFalse(len(capt.records))
            field.write(values_ai)
            self.assertTrue(len(capt.records))

        with self.capture_triggers(ai_field_cron_id) as capt:
            self.env["test.ai.fields.no.ai"].create({"name": "Record"})
            self.assertTrue(len(capt.records))

    def test_ai_properties_cron_trigger(self):
        ai_properties_cron = self.env.ref("ai_fields.ir_cron_fill_ai_fields").id
        definition_no_ai = self.env["test.ai.fields.parent"].create(
            {"properties_definition": []}
        )
        definition_with_ai = self.env["test.ai.fields.parent"].create(
            {
                "properties_definition": [
                    {
                        "name": "ai_property",
                        "type": "char",
                        "ai": True,
                        "system_prompt": "AI Prompt",
                    }
                ]
            }
        )

        with self.capture_triggers(ai_properties_cron) as capt:
            self.env["test.ai.fields.model"].create({"parent_id": definition_no_ai.id})
            self.assertFalse(len(capt.records))

        with self.capture_triggers(ai_properties_cron) as capt:
            definition_no_ai.write(
                {
                    "properties_definition": [
                        {
                            "name": "new_ai_property",
                            "type": "char",
                            "ai": True,
                            "system_prompt": "Another AI Prompt",
                        }
                    ]
                }
            )
            self.assertTrue(len(capt.records))

        definition_no_ai.properties_definition = []
        record = self.env["test.ai.fields.model"].create(
            {"parent_id": definition_with_ai.id}
        )
        with self.capture_triggers(ai_properties_cron) as capt:
            record.write({"parent_id": definition_no_ai.id})
            record.flush_recordset()
            self.assertFalse(len(capt.records))

        record = self.env["test.ai.fields.model"].create(
            {"parent_id": definition_no_ai.id}
        )
        with self.capture_triggers(ai_properties_cron) as capt:
            record.parent_id = definition_with_ai
            self.assertTrue(len(capt.records))

        with self.capture_triggers(ai_properties_cron) as capt:
            self.env["test.ai.fields.model"].create(
                {"parent_id": definition_with_ai.id}
            )
            self.assertTrue(len(capt.records))


@tagged("post_install", "-at_install")
class TestAiFields(TransactionCase):
    def _mock_llm_api_get_token(self):
        def _mock_get_api_token(self):
            return "dummy"

        return patch.object(LLMApiService, "_get_api_token", _mock_get_api_token)

    def test_ai_field_cron_fields(self):

        def _mocked_llm_api_request(self, method, endpoint, headers, body):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "text": json_dumps(
                                    {
                                        "value": f"response value {body['input'][1]['content'][0]['text']}",
                                        "is_resolved": True,
                                    }
                                )
                            }
                        ],
                    }
                ]
            }

        model = self.env["test.ai.fields.model"]

        field_definitions = [
            {
                "name": "x_ai_char",
                "ttype": "char",
                "ai": True,
                "system_prompt": "char prompt",
            },
            {
                "name": "x_ai_text",
                "ttype": "text",
                "ai": True,
                "system_prompt": "text prompt",
            },
            {
                "name": "x_ai_html",
                "ttype": "html",
                "ai": True,
                "system_prompt": "html prompt",
            },
            {
                "name": "x_ai_integer",
                "ttype": "integer",
                "ai": True,
                "system_prompt": "int prompt",
            },
            {
                "name": "x_ai_boolean",
                "ttype": "boolean",
                "ai": True,
                "system_prompt": "bool prompt",
            },
        ]

        ai_fields = {
            f["name"]: self.env["ir.model.fields"].create(
                f | {"model_id": self.env["ir.model"]._get("test.ai.fields.model").id}
            )
            for f in field_definitions
        }

        records = model.create(
            [
                {
                    "x_ai_char": None,
                    "x_ai_text": None,
                    "x_ai_html": None,
                    "x_ai_integer": 0,
                    "x_ai_boolean": False,
                },
                {
                    "x_ai_char": "",
                    "x_ai_text": "",
                    "x_ai_html": "",
                    "x_ai_integer": 0,
                    "x_ai_boolean": False,
                },
                {
                    "x_ai_char": "existing",
                    "x_ai_text": "existing",
                    "x_ai_html": "<p>existing</p>",
                    "x_ai_integer": 5,
                    "x_ai_boolean": True,
                },
            ]
        )

        ai_fields["x_ai_char"].write({"ai_domain": [["id", "!=", records[0].id]]})

        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "SELECT id, x_ai_char, x_ai_text, x_ai_html, x_ai_integer, x_ai_boolean FROM test_ai_fields_model WHERE id = ANY(%s)",
                records.ids,
            )
        )
        result = {row[0]: row[1:] for row in self.env.cr.fetchall()}

        self.assertEqual(result[records[0].id], (None, None, None, 0, False))
        self.assertEqual(result[records[1].id], ("", "", "", 0, False))
        self.assertEqual(
            result[records[2].id], ("existing", "existing", "<p>existing</p>", 5, True)
        )

        with (
            patch.object(LLMApiService, "_request", _mocked_llm_api_request),
            self.sync_env_with_side_cursors(),
            self._mock_llm_api_get_token(),
        ):
            self.env.ref("ai_fields.ir_cron_fill_ai_fields").method_direct_trigger()

        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "SELECT id, x_ai_char, x_ai_text, x_ai_html, x_ai_integer, x_ai_boolean FROM test_ai_fields_model WHERE id = ANY(%s)",
                records.ids,
            )
        )
        result = {row[0]: row[1:] for row in self.env.cr.fetchall()}

        self.assertEqual(
            result[records[0].id],
            (
                None,
                "response value text prompt",
                "<p>response value html prompt</p>",
                0,
                False,
            ),
            "Textual fields should have been updated (except char which is excluded by ai_domain)",
        )
        self.assertEqual(
            result[records[1].id],
            ("", "", "", 0, False),
            "No field should have been updated",
        )
        self.assertEqual(
            result[records[2].id],
            ("existing", "existing", "<p>existing</p>", 5, True),
            "No field should have been updated",
        )

    def test_ai_field_cron_properties(self):

        def _mocked_llm_api_request(self, method, endpoint, headers, body):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "text": json_dumps(
                                    {
                                        "value": f"response value {body['input'][1]['content'][0]['text']}"
                                    }
                                )
                            }
                        ],
                    }
                ]
            }

        parent = self.env["test.ai.fields.parent"].create({})

        record_0 = self.env["test.ai.fields.model"].create({})
        record_1 = self.env["test.ai.fields.model"].create({"parent_id": parent.id})

        parent.write(
            {
                "properties_definition": [
                    {
                        "type": "char",
                        "name": "char",
                        "ai": True,
                        "system_prompt": 'id=<span data-ai-field="id">id</span>',
                    }
                ]
            }
        )

        records = record_2, record_3, record_4, record_5 = self.env[
            "test.ai.fields.model"
        ].create(
            [
                {
                    "parent_id": parent.id,
                    "properties": [{"type": "char", "name": "char"}],
                },
                {
                    "parent_id": parent.id,
                    "properties": [{"type": "char", "name": "char", "value": ""}],
                },
                {
                    "parent_id": parent.id,
                    "properties": [{"type": "char", "name": "char", "value": False}],
                },
                {
                    "parent_id": parent.id,
                    "properties": [{"type": "char", "name": "char"}],
                },
            ]
        )
        records |= record_0 | record_1

        parent.write(
            {
                "properties_definition": [
                    {
                        "type": "char",
                        "name": "char",
                        "ai": True,
                        "system_prompt": 'id=<span data-ai-field="id">id</span>',
                        "ai_domain": [["id", "!=", record_2.id]],
                    }
                ]
            }
        )

        self.env.cr.execute(
            SQL(
                "SELECT id, properties FROM test_ai_fields_model WHERE id = ANY(%s)",
                records.ids,
            )
        )
        result = dict(self.env.cr.fetchall())
        self.assertEqual(result.get(record_0.id), None)
        self.assertEqual(result.get(record_1.id), None)
        self.assertEqual(result.get(record_2.id), {})
        self.assertEqual(result.get(record_3.id), {"char": False})
        self.assertEqual(result.get(record_4.id), {"char": False})
        self.assertEqual(result.get(record_5.id), {})

        with (
            patch.object(LLMApiService, "_request", _mocked_llm_api_request),
            self.sync_env_with_side_cursors(),
            self._mock_llm_api_get_token(),
        ):
            self.env.ref("ai_fields.ir_cron_fill_ai_fields").method_direct_trigger()
        self.env.flush_all()

        self.env.cr.execute(
            SQL(
                "SELECT id, properties FROM test_ai_fields_model WHERE id = ANY(%s)",
                records.ids,
            )
        )
        result = dict(self.env.cr.fetchall())
        self.assertEqual(result.get(record_0.id), None)
        self.assertEqual(
            result.get(record_1.id),
            {
                "char": f"response value id={{{{id}}}}\n# Context Dict\n{json.dumps({'test.ai.fields.model': [{'id': record_1.id}]}, indent=2)}\nThe current record is {{'model': test.ai.fields.model, 'id': {record_1.id}}}"
            },
        )
        self.assertEqual(
            result.get(record_2.id),
            {},
            "The AI domain should have prevented the update of that record",
        )
        self.assertEqual(result.get(record_3.id), {"char": False})
        self.assertEqual(result.get(record_4.id), {"char": False})
        self.assertEqual(
            result.get(record_5.id),
            {
                "char": f"response value id={{{{id}}}}\n# Context Dict\n{json.dumps({'test.ai.fields.model': [{'id': record_5.id}]}, indent=2)}\nThe current record is {{'model': test.ai.fields.model, 'id': {record_5.id}}}"
            },
        )

    def test_get_ai_context(self):
        partner_1, partner_2 = self.env["res.partner"].create(
            [
                {
                    "name": "partner 1",
                    "bank_account_ids": [
                        Command.create({"acc_number": f"bank_{i}", "note": f"note {i}"})
                        for i in range(3)
                    ],
                },
                {
                    "name": "partner 2",
                    "bank_account_ids": [
                        Command.create({"acc_number": f"bank_{i}", "note": f"note {i}"})
                        for i in range(2)
                    ],
                },
            ]
        )
        vals, files = partner_1._get_ai_context(
            ["name", "bank_account_ids.acc_number", "bank_account_ids.note"]
        )
        vals = json_loads(vals)
        self.assertEqual(len(vals), 2)
        self.assertEqual(
            vals["res.partner"],
            [
                {
                    "id": partner_1.id,
                    "bank_account_ids": {
                        "model": "res.partner.bank.account",
                        "ids": partner_1.bank_account_ids.ids,
                    },
                    "name": partner_1.name,
                }
            ],
        )
        self.assertCountEqual(
            vals["res.partner.bank.account"],
            partner_1.bank_account_ids.read(["acc_number", "note"]),
        )
        self.assertFalse(files)

        pdf_datas = base64.b64encode(b"%PDF-1.4\ndummy\n%%EOF")
        png_datas = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        txt_datas = base64.b64encode(b"My txt content")

        record = self.env["test.ai.read.model"].create(
            {
                "currency_id": self.env.ref("base.EUR").id,
                "price": "123.45",
                "message_ids": [
                    Command.create(
                        {
                            "author_id": partner_1.id,
                            "body": '<div data-oe-version="2.0"><span class="h2-fs"><font style="background-color:red">Hello World</font></span></div>',
                            "attachment_ids": [
                                Command.create(
                                    {"name": "dummy pdf", "datas": pdf_datas}
                                ),
                                Command.create(
                                    {"name": "dummy png", "datas": png_datas}
                                ),
                                Command.create(
                                    {"name": "dummy txt", "datas": txt_datas}
                                ),
                            ],
                            "model": "test.ai.read.model",
                        }
                    )
                ],
                "message_partner_ids": [partner_1.id, partner_2.id],
            }
        )
        vals, files = record._get_ai_context(
            [
                "price",
                "message_ids.body",
                "message_ids.attachment_ids",
                "create_date",
                "message_partner_ids.bank_account_ids.acc_number",
            ]
        )
        vals = json_loads(vals)
        self.assertEqual(len(vals), 5)
        self.assertEqual(
            vals["test.ai.read.model"],
            [
                {
                    "id": record.id,
                    "create_date": fields.Datetime.to_string(record.create_date),
                    "message_ids": {
                        "model": "mail.message",
                        "ids": record.message_ids.ids,
                    },
                    "message_partner_ids": {
                        "model": "res.partner",
                        "ids": record.message_partner_ids.ids,
                    },
                    "price": "123.45\xa0€",
                }
            ],
        )
        self.assertCountEqual(
            vals["mail.message"],
            [
                {
                    "id": record.message_ids[0].id,
                    "body": "Test AI Read created",
                    "attachment_ids": {
                        "model": "ir.attachment",
                        "ids": record.message_ids[0].attachment_ids.ids,
                    },
                },
                {
                    "id": record.message_ids[1].id,
                    "body": "Hello World",
                    "attachment_ids": {
                        "model": "ir.attachment",
                        "ids": record.message_ids[1].attachment_ids.ids,
                    },
                },
            ],
        )

        self.assertEqual(
            {v["id"] for v in vals["ir.attachment"]},
            set(record.message_ids[1].attachment_ids.ids),
        )
        self.assertEqual(
            {v["file"] for v in vals["ir.attachment"]},
            {"<file_#1>", "<file_#2>", "<file_#3>"},
        )
        self.assertCountEqual(
            vals["res.partner"],
            [
                {
                    "id": record.message_partner_ids[0].id,
                    "bank_account_ids": {
                        "model": "res.partner.bank.account",
                        "ids": record.message_partner_ids[0].bank_account_ids.ids,
                    },
                },
                {
                    "id": record.message_partner_ids[1].id,
                    "bank_account_ids": {
                        "model": "res.partner.bank.account",
                        "ids": record.message_partner_ids[1].bank_account_ids.ids,
                    },
                },
            ],
        )
        self.assertCountEqual(
            vals["res.partner.bank.account"],
            record.message_partner_ids.bank_account_ids.read(["acc_number"]),
        )
        contents = {
            "application/pdf": pdf_datas.decode(),
            "image/png": png_datas.decode(),
            "text/plain": "My txt content",
        }
        self.assertEqual(
            files,
            [
                {
                    "mimetype": attachment.mimetype,
                    "value": contents[attachment.mimetype],
                    "file_ref": f"<file_#{index}>",
                }
                for index, attachment in enumerate(
                    record.message_ids[1].attachment_ids, start=1
                )
            ],
        )

        partner_2.name = "_" * 1000
        for field_path in (
            "message_partner_ids",
            "message_partner_ids.name",
            "message_partner_ids.display_name",
        ):
            vals, _files = record._get_ai_context([field_path])
            self.assertNotIn(partner_2.name, vals)
            self.assertIn(partner_2._ai_truncate(partner_2.name), vals)

        tmp_record = record.new(origin=record)
        vals, files = tmp_record._get_ai_context(
            ["message_partner_ids.bank_account_ids"]
        )
        vals = json_loads(vals)
        self.assertEqual(vals["test.ai.read.model"][0]["id"], tmp_record.id.origin)
        self.assertEqual(
            vals["test.ai.read.model"][0]["message_partner_ids"]["ids"],
            [_id.origin for _id in tmp_record.message_partner_ids._ids],
        )
        self.assertCountEqual(
            vals["res.partner"],
            [
                {
                    "id": tmp_record.message_partner_ids[0].id.origin,
                    "bank_account_ids": {
                        "model": "res.partner.bank.account",
                        "ids": [
                            _id.origin
                            for _id in tmp_record.message_partner_ids[
                                0
                            ].bank_account_ids._ids
                        ],
                    },
                },
                {
                    "id": tmp_record.message_partner_ids[1].id.origin,
                    "bank_account_ids": {
                        "model": "res.partner.bank.account",
                        "ids": [
                            _id.origin
                            for _id in tmp_record.message_partner_ids[
                                1
                            ].bank_account_ids._ids
                        ],
                    },
                },
            ],
        )

        new_record = self.env["test.ai.read.model"].new(
            {
                "message_partner_ids": [
                    [0, "virtual_1", {"name": "Frank"}],
                    [0, "virtual_2", {"name": "Bill"}],
                ]
            }
        )
        vals, files = new_record._get_ai_context(["message_partner_ids.name"])
        vals = json_loads(vals)
        self.assertEqual(vals["test.ai.read.model"][0]["id"], str(new_record.id))
        self.assertEqual(
            vals["test.ai.read.model"][0]["message_partner_ids"]["ids"],
            [str(_id) for _id in new_record.message_partner_ids._ids],
        )
        self.assertCountEqual(
            vals["res.partner"],
            [
                {"id": str(new_record.message_partner_ids[0].id), "name": "Frank"},
                {"id": str(new_record.message_partner_ids[1].id), "name": "Bill"},
            ],
        )

    def test_ai_read_dirty_binary(self):
        record = self.env["test.ai.read.model"].create({})
        changed_png_data = base64.b64encode(b"unsaved-changed-png")
        dirty_record = record.new({"new_binary_field": changed_png_data}, origin=record)

        __, files_dict = dirty_record._ai_read(["new_binary_field"], {})

        self.assertTrue(
            any(
                b"unsaved-changed-png" in base64.b64decode(f["value"])
                for f in files_dict.values()
            ),
            "Expected changed (unsaved) PNG data in files_dict for Binary field",
        )

    def test_ai_field_sanitize(self):
        system_prompt = '<p><span data-ai-field="name">name</span> <img src="x" onerror="alert(1)"/></p>'
        expected = '<p><span data-ai-field="name">name</span> <img src="x"/></p>'
        properties_definition = [
            {
                "type": "char",
                "name": "char",
                "ai": True,
                "system_prompt": system_prompt,
            }
        ]
        parent = self.env["test.ai.fields.parent"].create(
            {"properties_definition": copy.deepcopy(properties_definition)}
        )

        self.assertEqual(parent.properties_definition[0]["system_prompt"], expected)
        record = self.env["test.ai.fields.model"].create({"parent_id": parent.id})
        self.assertEqual(
            record.read(["properties"])[0]["properties"][0]["system_prompt"], expected
        )

        self.env.cr.execute(
            "SELECT properties_definition[0]->'system_prompt' FROM test_ai_fields_parent WHERE id = %s",
            [parent.id],
        )
        property_prompt = self.env.cr.fetchone()[0]
        self.assertEqual(property_prompt, expected)

        self.assertIn("onerror", str(properties_definition))
        self.env.cr.execute(
            "UPDATE test_ai_fields_parent SET properties_definition = %s WHERE id = %s",
            [json_dumps(properties_definition), parent.id],
        )
        self.env.flush_all()

        self.assertEqual(
            parent.read(["properties_definition"])[0]["properties_definition"][0][
                "system_prompt"
            ],
            expected,
        )
        self.assertEqual(
            record.read(["properties"])[0]["properties"][0]["system_prompt"], expected
        )

        field = self.env["ir.model.fields"].create(
            {
                "name": "x_ai_char",
                "model_id": self.env["ir.model"]._get("test.ai.fields.no.ai").id,
                "ttype": "char",
                "ai": True,
                "system_prompt": system_prompt,
            }
        )
        self.assertEqual(field.system_prompt, expected)

        self.env["ir.model.fields"].create(
            {
                "name": "x_ai_html",
                "model_id": self.env["ir.model"]._get("test.ai.fields.model").id,
                "ttype": "html",
                "ai": True,
                "system_prompt": "prompt",
            }
        )

        def _mocked_llm_api_request(self, method, endpoint, headers, body):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "text": json_dumps(
                                    {
                                        "value": '<p><img src="x" onerror="alert(1)"/></p>'
                                    }
                                )
                            }
                        ],
                    }
                ]
            }

        with (
            patch.object(LLMApiService, "_request", _mocked_llm_api_request),
            self._mock_llm_api_get_token(),
        ):
            value = record.get_ai_field_value("x_ai_html", None)
            self.assertEqual(value, '<p><img src="x"></p>')

        record.write(
            {
                "properties": [
                    {
                        "type": "html",
                        "name": "test_html",
                        "ai": True,
                        "system_prompt": "system_prompt",
                        "definition_changed": True,
                    }
                ],
            }
        )
        record.flush_recordset()
        with (
            patch.object(LLMApiService, "_request", _mocked_llm_api_request),
            self._mock_llm_api_get_token(),
        ):
            value = record.get_ai_property_value("properties.test_html", None)
        self.assertEqual(value, '<p><img src="x"></p>')

    def test_ai_field_unresolved_request(self):
        self.env["ir.model.fields"].create(
            {
                "name": "x_ai_char",
                "model_id": self.env["ir.model"]._get("test.ai.fields.model").id,
                "ttype": "char",
                "ai": True,
                "system_prompt": "Hello",
            }
        )
        record = self.env["test.ai.fields.model"].create({})

        def _mocked_llm_api_request(self, method, endpoint, headers, body):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "text": json_dumps(
                                    {
                                        "value": "Sorry",
                                        "could_not_resolve": True,
                                        "unresolved_cause": "Missing context",
                                    }
                                )
                            }
                        ],
                    }
                ]
            }

        with (
            patch.object(LLMApiService, "_request", _mocked_llm_api_request),
            self._mock_llm_api_get_token(),
            self.assertRaises(UnresolvedQuery) as cm_1,
        ):
            record.get_ai_field_value("x_ai_char", None)
        self.assertEqual(str(cm_1.exception), "Missing context")

        record.write(
            {
                "parent_id": self.env["test.ai.fields.parent"]
                .create(
                    {
                        "properties_definition": [
                            {
                                "type": "char",
                                "name": "char",
                                "ai": True,
                                "system_prompt": "Hello",
                            }
                        ]
                    }
                )
                .id
            }
        )

        with (
            patch.object(LLMApiService, "_request", _mocked_llm_api_request),
            self._mock_llm_api_get_token(),
            self.assertRaises(UnresolvedQuery) as cm_2,
        ):
            record.get_ai_property_value("properties.char", None)
        self.assertEqual(str(cm_2.exception), "Missing context")

    def test_fill_ai_field_exception(self):

        def _mocked_llm_api_request(self, method, endpoint, headers, body):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "text": json_dumps(
                                    {
                                        "value": "",
                                        "could_not_resolve": True,
                                        "unresolved_cause": "missing context",
                                    }
                                )
                            }
                        ],
                    }
                ]
            }

        model = self.env["test.ai.fields.model"]
        self.env["ir.model.fields"].create(
            {
                "name": "x_ai_char",
                "ttype": "char",
                "ai": True,
                "system_prompt": "char prompt",
                "model_id": self.env["ir.model"]._get(model._name).id,
            }
        )
        record = model.create({})
        self.env.flush_all()
        self.env.cr.execute(
            SQL("SELECT x_ai_char FROM test_ai_fields_model WHERE id = %s", record.id)
        )
        res = self.env.cr.fetchone()
        self.assertEqual(res[0], None)
        record._update_ai_field(model._fields.get("x_ai_char"))
        self.env.flush_all()
        self.env.cr.execute(
            SQL("SELECT x_ai_char FROM test_ai_fields_model WHERE id = %s", record.id)
        )
        res = self.env.cr.fetchone()
        self.assertEqual(res[0], "")

    def test_fill_ai_property_exception(self):

        def _mocked_llm_api_request(self, method, endpoint, headers, body):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "text": json_dumps(
                                    {
                                        "value": "",
                                        "could_not_resolve": True,
                                        "unresolved_cause": "missing context",
                                    }
                                )
                            }
                        ],
                    }
                ]
            }

        parent = self.env["test.ai.fields.parent"].create({})
        ai_char_p_def = {
            "type": "char",
            "name": "char",
            "ai": True,
            "system_prompt": "hey",
        }
        parent.write({"properties_definition": [ai_char_p_def]})

        record = self.env["test.ai.fields.model"].create(
            [
                {
                    "parent_id": parent.id,
                    "properties": [{"type": "char", "name": "char"}],
                },
            ]
        )

        self.env.flush_all()
        self.env.cr.execute(
            SQL("SELECT properties FROM test_ai_fields_model WHERE id = %s", record.id)
        )
        res = self.env.cr.fetchone()
        self.assertEqual(res[0], {})
        record._update_ai_property("properties", ai_char_p_def)
        self.env.flush_all()
        self.env.cr.execute(
            SQL("SELECT properties FROM test_ai_fields_model WHERE id = %s", record.id)
        )
        res = self.env.cr.fetchone()
        self.assertEqual(res[0], {"char": False})
