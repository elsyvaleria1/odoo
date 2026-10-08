import logging

from odoo.service.model import call_kw
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import PosOpenSessionCommon, TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosConfigSequences(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config

    def test_session_name_uses_the_config_company_sequence(self):
        other_company = self.env["res.company"].create({"name": "Active company"})
        sequence = (
            self.env["ir.sequence"]
            .sudo()
            .create(
                {
                    "name": "Config company sessions",
                    "code": "pos.session",
                    "company_id": self.config.company_id.id,
                    "prefix": "CONFIG/",
                    "padding": 3,
                }
            )
        )
        self.env["ir.sequence"].sudo().create(
            {
                "name": "Other company sessions",
                "code": "pos.session",
                "company_id": other_company.id,
                "prefix": "OTHER/",
            }
        )

        name = self.config.with_company(other_company)._get_next_session_name()

        self.assertEqual(name, "CONFIG/001")
        self.assertEqual(sequence.number_next_actual, 2)

    def test_sequence_fallback_and_duplicate_company_priority(self):
        Sequence = self.env["ir.sequence"].sudo()
        Sequence.search([("code", "=", "pos.session")]).unlink()
        self.assertEqual(self.config._get_next_session_name(), "/")
        shared = Sequence.create(
            {
                "name": "Shared",
                "code": "pos.session",
                "company_id": False,
                "prefix": "GLOBAL/",
            }
        )
        self.assertEqual(self.config._get_next_session_name(), "GLOBAL/1")
        first = Sequence.create(
            {
                "name": "First",
                "code": "pos.session",
                "company_id": self.config.company_id.id,
                "prefix": "FIRST/",
            }
        )
        second = first.copy({"name": "Second", "prefix": "SECOND/"})

        self.assertEqual(self.config._get_next_session_name(), "FIRST/1")

        self.assertEqual(first.number_next_actual, 2)
        self.assertEqual(second.number_next_actual, 1)
        self.assertEqual(shared.number_next_actual, 2)

    def test_order_refs_survive_a_prefixed_sequence(self):
        self.config.order_backend_seq_id.sudo().prefix = "/AA"
        self.env.invalidate_all()
        reference, tracking_number = self.config._get_next_order_refs()
        self.assertTrue(reference)
        self.assertTrue(tracking_number.isdigit())

    def test_deleting_a_config_deletes_its_sequences(self):
        cfg = self.env["pos.config"].create({"name": "AuditSeqCfg"})
        seq_ids = (
            cfg.order_seq_id
            | cfg.order_backend_seq_id
            | cfg.order_line_seq_id
            | cfg.device_seq_id
        )
        self.assertEqual(len(seq_ids), 4, "expected 4 sequences created")
        seq_ids_list = seq_ids.ids
        cfg.unlink()
        survivors = self.env["ir.sequence"].browse(seq_ids_list).exists()
        _logger.info("Sequences surviving the deletion: %s", survivors.mapped("name"))
        self.assertFalse(
            survivors,
            "%d per-config sequence(s) leaked on unlink: %s"
            % (len(survivors), survivors.mapped("name")),
        )

    def test_pos_manager_can_delete_a_config(self):
        manager = self.env["res.users"].create(
            {
                "name": "PoS Manager",
                "login": "audit_pos_manager",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("point_of_sale.group_pos_manager").id,
                            self.env.ref("base.group_user").id,
                        ],
                    )
                ],
            }
        )
        config = self.config.copy({"name": "to-delete"})
        sequences = (
            config.order_seq_id
            | config.order_backend_seq_id
            | config.order_line_seq_id
            | config.device_seq_id
        )
        call_kw(self.env["pos.config"].with_user(manager), "unlink", [[config.id]], {})
        self.assertFalse(config.exists())
        self.assertFalse(sequences.exists())


@tagged("post_install", "-at_install")
class TestPosConfigSequenceCodes(PosOpenSessionCommon):
    def test_the_four_config_sequences_have_distinct_codes(self):
        config = self.pos_config_usd
        codes = [
            config.order_seq_id.code,
            config.order_backend_seq_id.code,
            config.order_line_seq_id.code,
            config.device_seq_id.code,
        ]
        self.assertEqual(len(set(codes)), 4, codes)
