from odoo.tests import HttpCase, tagged

MOLBLOCK = """water
     RDKit          3D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.1173 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    0.7572   -0.4692 H   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -0.7572   -0.4692 H   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  1  3  1  0
M  END
"""

WAIT_FOR_CANVAS = """
const timer = setInterval(() => {
    if (document.querySelector(".o_molecule_viewer_3d canvas")) {
        clearInterval(timer);
        console.log("test successful");
    }
}, 200);
"""


@tagged("post_install", "-at_install")
class TestMoleculeViewer(HttpCase):
    def test_viewer_renders_canvas(self):
        compound = self.env["molecular.compound"].create(
            {"name": "water", "identity_key": "SH1-WATER"}
        )
        self.env["molecular.structure"].create(
            {
                "compound_id": compound.id,
                "kind": "3d_conformer",
                "molblock": MOLBLOCK,
            }
        )
        self.browser_js(
            f"/odoo/action-molecular_screening.molecular_compound_action/{compound.id}",
            WAIT_FOR_CANVAS,
            login="admin",
            timeout=60,
        )
