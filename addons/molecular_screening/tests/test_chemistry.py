from odoo.tests import BaseCase, tagged

from ..tools.chemistry import compute_identity
from ..tools.molfile import parse_molblock
from .common import SDF_SAMPLE
from .test_molfile import CHARGED

# Same molecule as CHARGED, written with its atoms in another order
REORDERED = """anion reordered
     RDKit          2D

  4  3  0  0  0  0  0  0  0  0999 V2000
    2.1000    1.2000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    1.4000    0.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
    2.1000   -1.2000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
  2  3  1  0
  2  4  1  0
M  CHG  2   2   1   3  -1
M  END
"""


@tagged("post_install", "-at_install")
class TestChemistry(BaseCase):
    def _identity(self, molblock):
        atoms, bonds = parse_molblock(molblock)
        return compute_identity(molblock=molblock, atoms=atoms, bonds=bonds)

    def test_identity_survives_atom_reordering(self):
        first, second = self._identity(CHARGED), self._identity(REORDERED)
        self.assertEqual(first["identity_key"], second["identity_key"])
        self.assertTrue(first["method"])

    def test_different_molecules_differ(self):
        water = SDF_SAMPLE.split("$$$$")[0]
        self.assertNotEqual(
            self._identity(CHARGED)["identity_key"],
            self._identity(water)["identity_key"],
        )

    def test_smiles_only_still_yields_a_key(self):
        identity = compute_identity(smiles="O=C(O)CNCP(=O)(O)O")
        self.assertTrue(identity["identity_key"])
        self.assertTrue(identity["method"])

    def test_nothing_to_identify(self):
        with self.assertRaises(ValueError):
            compute_identity()
