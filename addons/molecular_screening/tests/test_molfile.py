from odoo.tests import BaseCase, tagged

from ..tools.molfile import parse_molblock

# Nitromethane anion drawn with a charged pair and a reversed bond record, so
# both the M CHG block and the atom-order normalisation get exercised.
CHARGED = """anion
     RDKit          2D

  4  3  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4000    0.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
    2.1000    1.2000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    2.1000   -1.2000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  2  1  1  0
  2  3  2  0
  4  2  1  0
M  CHG  2   2   1   4  -1
M  END
"""


@tagged("post_install", "-at_install")
class TestMolfile(BaseCase):
    def test_atoms_and_charges(self):
        atoms, _bonds = parse_molblock(CHARGED)
        self.assertEqual([atom["element"] for atom in atoms], ["C", "N", "O", "O"])
        self.assertEqual([atom["idx"] for atom in atoms], [1, 2, 3, 4])
        self.assertEqual([atom["formal_charge"] for atom in atoms], [0, 1, 0, -1])
        self.assertAlmostEqual(atoms[1]["x"], 1.4)

    def test_bonds_are_normalised(self):
        _atoms, bonds = parse_molblock(CHARGED)
        # Every record is stored with its lower index first, whichever way the
        # file wrote it, so one bond cannot enter twice reversed.
        self.assertTrue(all(bond["atom_a"] < bond["atom_b"] for bond in bonds))
        self.assertEqual(
            sorted(
                (bond["atom_a"], bond["atom_b"], bond["bond_order"]) for bond in bonds
            ),
            [(1, 2, 1), (2, 3, 2), (2, 4, 1)],
        )

    def test_aromatic_flag(self):
        aromatic = CHARGED.replace("  2  3  2  0", "  2  3  4  0")
        _atoms, bonds = parse_molblock(aromatic)
        flagged = [bond for bond in bonds if bond["aromatic"]]
        self.assertEqual(len(flagged), 1)
        # An aromatic record has no Kekulé order of its own, so it is kept as 1
        self.assertEqual(flagged[0]["bond_order"], 1)

    def test_rejects_v3000_and_garbage(self):
        with self.assertRaises(ValueError):
            parse_molblock(CHARGED.replace("V2000", "V3000"))
        with self.assertRaises(ValueError):
            parse_molblock("not\na\nmolblock\n")
