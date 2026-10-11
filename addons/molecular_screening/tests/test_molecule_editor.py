from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from .fixtures import ACETONITRILE, BENZENE, EXPECTED, OVERLOADED

SKETCH_FLOW = """
const waitFor = (selector, test) =>
    new Promise((resolve, reject) => {
        const deadline = Date.now() + 25000;
        const timer = setInterval(() => {
            const el = document.querySelector(selector);
            if (el && (!test || test(el))) {
                clearInterval(timer);
                resolve(el);
            } else if (Date.now() > deadline) {
                clearInterval(timer);
                reject(new Error("timeout waiting for " + selector));
            }
        }, 150);
    });
const byText = (selector, text) =>
    [...document.querySelectorAll(selector)].find((el) => el.textContent.trim() === text);

(async () => {
    await waitFor(".o_molecule_editor canvas");
    byText(".o_molecule_editor button", "Benzene").click();
    await waitFor(".o_molecule_editor dd", () => {
        const cells = [...document.querySelectorAll(".o_molecule_editor dd")];
        return cells.length && cells[0].textContent.trim() === "C₆H₆";
    });
    const cells = [...document.querySelectorAll(".o_molecule_editor dd")].map((el) =>
        el.textContent.trim()
    );
    if (cells[1] !== "78.114") {
        throw new Error("average mass reads " + cells[1]);
    }
    const aromatic = [...document.querySelectorAll(".o_molecule_editor dt")].find(
        (el) => el.textContent.trim() === "Aromatic rings"
    );
    if (!aromatic || aromatic.nextElementSibling.textContent.trim() !== "1") {
        throw new Error("aromatic rings read " + aromatic?.nextElementSibling.textContent);
    }
    byText(".o_molecule_editor button", "Relax").click();
    await waitFor(".o_molecule_editor_viewer canvas");
    byText(".o_molecule_editor button", "Keep").click();
    const name = await waitFor('.o_field_widget[name="name"] input');
    name.value = "benzene-sketch";
    name.dispatchEvent(new Event("input", { bubbles: true }));
    name.dispatchEvent(new Event("change", { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 400));
    byText(".modal-footer button, .o_form_view button", "Save Compound").click();
    await waitFor(".o_form_view .o_field_widget[name='identity_key']");
    console.log("test successful");
})();
"""


@tagged("post_install", "-at_install")
class TestMoleculeEditorServer(TransactionCase):
    def test_compound_from_drawing(self):
        compound = self.env["molecular.compound"].create_from_molblock(
            BENZENE, vals={"name": "benzene", "origin": "diversity"}
        )
        self.assertEqual(compound.formula, EXPECTED["benzene"]["formula"])
        self.assertEqual(compound.structure_2d_id.generator, "molecule-editor")
        self.assertEqual(compound.structure_2d_id.atom_count, 6)
        self.assertEqual(compound.structure_2d_id.bond_count, 6)
        self.assertAlmostEqual(
            compound.molecular_weight, EXPECTED["benzene"]["weight"], places=2
        )
        self.assertEqual(compound.ring_count, 1)
        mass = compound.property_ids.filtered(lambda p: p.key == "mw")
        self.assertEqual(mass.method, "valence-table-v1")

    def test_same_drawing_is_one_compound(self):
        first = self.env["molecular.compound"].create_from_molblock(
            BENZENE, vals={"name": "benzene"}
        )
        second = self.env["molecular.compound"].create_from_molblock(BENZENE)
        self.assertEqual(first, second)
        self.assertEqual(len(first.structure_ids), 2)

    def test_exceeded_valence_stores_no_mass(self):
        compound = self.env["molecular.compound"].create_from_molblock(
            OVERLOADED, vals={"name": "overloaded"}
        )
        self.assertFalse(compound.property_ids.filtered(lambda p: p.key == "mw"))
        self.assertEqual(compound.molecular_weight, 0)

    def test_unreadable_drawing_is_refused(self):
        with self.assertRaises(UserError):
            self.env["molecular.compound"].create_from_molblock("not a molblock")
        with self.assertRaises(UserError):
            self.env["molecular.compound"].create_from_molblock(
                BENZENE.replace(" C   0", " Xx  0")
            )

    def test_sketch_wizard_saves_roles_and_geometries(self):
        campaign = self.env["molecular.screening.campaign"].create(
            {"name": "Sketching"}
        )
        sketch = self.env["wizard.molecular.sketch"].create(
            {
                "name": "acetonitrile",
                "campaign_id": campaign.id,
                "role": "candidate",
                "origin": "diversity",
                "molblock": ACETONITRILE,
                "molblock_3d": ACETONITRILE.replace("2D", "3D"),
            }
        )
        self.assertIn("C2H3N", sketch.summary)
        sketch.action_save()
        compound = sketch.compound_id
        self.assertEqual(compound.name, "acetonitrile")
        self.assertEqual(campaign.candidate_count, 1)
        self.assertEqual(
            sorted(compound.structure_ids.mapped("kind")),
            ["2d_drawing", "3d_conformer"],
        )

    def test_summary_reports_exceeded_valence(self):
        sketch = self.env["wizard.molecular.sketch"].create(
            {"name": "overloaded", "molblock": OVERLOADED}
        )
        self.assertIn("Valence exceeded", sketch.summary)


@tagged("post_install", "-at_install")
class TestMoleculeEditorBrowser(HttpCase):
    def test_draw_relax_and_save(self):
        self.browser_js(
            "/odoo/action-molecular_screening.molecular_sketch_action",
            SKETCH_FLOW,
            login="admin",
            timeout=90,
        )
        compound = self.env["molecular.compound"].search(
            [("name", "=", "benzene-sketch")]
        )
        self.assertEqual(len(compound), 1)
        self.assertEqual(compound.formula, "C6H6")
        self.assertEqual(
            sorted(compound.structure_ids.mapped("kind")),
            ["2d_drawing", "3d_conformer"],
        )
