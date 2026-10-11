from types import SimpleNamespace

from odoo.modules.registry import Registry
from odoo.tests.common import get_db_name, tagged

from .lint_case import LintCase

X2MANY_TYPES = ("one2many", "many2many")
BINARY_TYPES = ("binary", "image")


class PlantedField:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)


def storage_keys(field) -> frozenset[str]:
    keys = set()
    if field.company_dependent:
        keys.add("company")
    if field.translate:
        keys.add("lang")
    if field.type in BINARY_TYPES:
        keys.update(("bin_size", f"bin_size_{field.name}"))
    if field.type in X2MANY_TYPES or (field.compute and field.compute_sudo):
        keys.add("access")
    return frozenset(keys)


def reader_keys(field, depends_context) -> list[str]:
    if field.type in X2MANY_TYPES and not field.compute:
        return []
    exempt = storage_keys(field)
    return [key for key in depends_context if key not in exempt]


def reader_context_findings(models, field_depends_context) -> list[str]:
    found = []
    for model_name, model_cls in models:
        if model_cls._abstract:
            continue
        for field in model_cls._fields.values():
            if not field.store:
                continue
            keys = reader_keys(field, field_depends_context.get(field, ()))
            if keys:
                found.append(
                    f"{model_name}.{field.name} ({field._module}): {', '.join(keys)}"
                )
    return found


@tagged("-at_install", "post_install")
class TestStoredReaderContext(LintCase):
    def test_no_stored_field_depends_on_the_context_it_is_computed_in(self):
        registry = Registry(get_db_name())
        checked = sum(
            1
            for model_cls in registry.values()
            for field in model_cls._fields.values()
            if field.store
        )
        self.assertGreater(checked, 1000, "the scan reached almost no stored field")
        self.assert_ratchet(
            reader_context_findings(registry.items(), registry.field_depends_context),
            "stored_field_reader_context",
            "stored field(s) whose value depends on the context it is computed in",
            "A stored field has one column for every reader, and recomputation "
            "follows @api.depends only. A context dependency on it keeps one cache "
            "slot per context value, and the flush writes whichever slot it meets "
            "first (78b2667a8d37: an invoice's signer stayed the previous poster). "
            "Compute from the record's own data, or leave the field unstored; "
            "where the stored value is meant to be the acting user's (a default "
            "at creation, an edit), drop the declaration, which cannot make the "
            "column hold more than one answer. Transient models are not exempt: "
            "one request reads a wizard row through envs that differ in company, "
            "language or user (the send wizards render per recipient language), "
            "and each gets its own slot.",
        )

    def test_the_gate_reads_a_planted_fault(self):
        def field(name, type_="char", **attrs):
            return PlantedField(
                name=name,
                type=type_,
                store=attrs.pop("store", True),
                compute=attrs.pop("compute", "_compute_x"),
                compute_sudo=attrs.pop("compute_sudo", True),
                company_dependent=attrs.pop("company_dependent", False),
                translate=attrs.pop("translate", False),
                _module="planted",
                **attrs,
            )

        reader = field("reader")
        by_company = field("by_company", company_dependent=True, compute=None)
        translated = field("label", translate=True)
        image = field("image", "binary", compute=None)
        lines = field("line_ids", "one2many", compute=None)
        computed_lines = field("user_ids", "many2many")
        related_sudo = field("partner_id", "many2one")
        related_as_reader = field("owner_id", "many2one", compute_sudo=False)
        unstored = field("unstored", store=False)
        planted = {
            reader: ("uid",),
            by_company: ("company",),
            translated: ("lang",),
            image: ("bin_size", "bin_size_image"),
            lines: ("company", "access"),
            computed_lines: ("uid", "access"),
            related_sudo: ("access",),
            related_as_reader: ("access",),
            unstored: ("uid",),
        }
        self.assertEqual(reader_keys(by_company, ("company", "uid")), ["uid"])
        self.assertEqual(reader_keys(translated, ("lang", "company")), ["company"])
        self.assertEqual(
            reader_keys(reader, ("allowed_company_ids", "lang")),
            ["allowed_company_ids", "lang"],
        )
        model = SimpleNamespace(_abstract=False, _fields={f.name: f for f in planted})
        abstract = SimpleNamespace(_abstract=True, _fields={"reader": reader})
        self.assertEqual(
            sorted(
                reader_context_findings(
                    [("planted.model", model), ("planted.mixin", abstract)], planted
                )
            ),
            [
                "planted.model.owner_id (planted): access",
                "planted.model.reader (planted): uid",
                "planted.model.user_ids (planted): uid",
            ],
        )
