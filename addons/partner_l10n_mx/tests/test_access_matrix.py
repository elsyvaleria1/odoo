from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestPartnerL10nMxAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "employee_b": Persona(company="b"),
    }
    cells = (
        Cell(
            "l10n_mx.municipality",
            "municipality",
            note="a shared catalogue: written only by its loaders, under a privilege",
            employee_a="r",
            admin_a="r",
            employee_b="r",
        ),
        Cell(
            "l10n_mx.postal_code",
            "postal_code",
            note="a shared catalogue: written only by the SEPOMEX import and the "
            "geometry loader, under a privilege",
            employee_a="r",
            admin_a="r",
            employee_b="r",
        ),
    )

    @classmethod
    def build(cls):
        state = cls.env["res.country.state"].create(
            {
                "name": "Matrix State",
                "code": "MTX",
                "country_id": cls.env.ref("base.mx").id,
            }
        )
        municipality = cls.env["l10n_mx.municipality"].create(
            {"name": "Matrix", "code": "001", "state_id": state.id}
        )
        return {
            "municipality": municipality,
            "postal_code": cls.env["l10n_mx.postal_code"].create(
                {
                    "code": "99961",
                    "state_id": state.id,
                    "municipality_id": municipality.id,
                }
            ),
        }
