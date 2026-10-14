import importlib.util
import re
from pathlib import Path

import polib

from odoo.tests import TransactionCase
from odoo.tools import SQL

BASE = Path(__file__).parents[1]
INDENTED = re.compile(r"\n\s")


def _load_industry_names_migration():
    path = BASE / "migrations/1.161/post-industry-names.py"
    spec = importlib.util.spec_from_file_location("industry_names_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _squashed(text: str) -> str:
    return " ".join(text.split())


class TestShippedText(TransactionCase):
    def test_no_shipped_label_carries_its_data_file_s_indentation(self):
        indented = []
        data = self.env["ir.model.data"].search([("module", "=", "base")])
        for model, rows in data.grouped("model").items():
            if model not in self.env:
                continue
            records = (
                self.env[model]
                .with_context(active_test=False, lang="en_US")
                .browse(rows.mapped("res_id"))
                .exists()
            )
            labels = [
                name
                for name, field in records._fields.items()
                if field.type == "char" and field.translate is True and field.store
            ]
            indented += [
                f"{record._name},{record.id}.{name}"
                for record in records
                for name in labels
                if INDENTED.search(record[name] or "")
            ]
        self.assertEqual(indented, [])

    def test_no_translation_is_left_behind_by_a_whitespace_change(self):
        stranded = {}
        for path in sorted((BASE / "i18n").glob("*.po")):
            catalog = polib.pofile(str(path))
            kept = {
                _squashed(entry.msgid)
                for entry in catalog.obsolete_entries()
                if entry.msgstr and "fuzzy" not in entry.flags
            }
            if lost := [
                entry.msgid
                for entry in catalog
                if not entry.obsolete
                and not entry.msgstr
                and "fuzzy" not in entry.flags
                and _squashed(entry.msgid) in kept
            ]:
                stranded[path.name] = len(lost)
        self.assertEqual(stranded, {})

    def test_the_upgrade_unwraps_the_industry_names_a_reformat_wrapped(self):
        industry = self.env.ref("base.res_partner_industry_G")
        full_name = (
            "G - WHOLESALE AND RETAIL TRADE; REPAIR OF MOTOR VEHICLES AND MOTORCYCLES"
        )
        wrapped = full_name.replace(" MOTORCYCLES", "\n            MOTORCYCLES")
        self.env.cr.execute(
            SQL(
                "UPDATE res_partner_industry SET full_name = "
                "jsonb_build_object('en_US', %s::text, 'es_ES', 'G - VENTA') "
                "WHERE id = %s",
                wrapped,
                industry.id,
            )
        )

        _load_industry_names_migration().migrate(self.env.cr, "1.160")

        self.env.cr.execute(
            SQL("SELECT full_name FROM res_partner_industry WHERE id = %s", industry.id)
        )
        self.assertEqual(
            self.env.cr.fetchone()[0], {"en_US": full_name, "es_ES": "G - VENTA"}
        )
