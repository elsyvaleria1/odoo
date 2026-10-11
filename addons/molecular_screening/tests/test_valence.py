from odoo.tests import BaseCase, tagged

from ..tools import valence
from ..tools.molfile import parse_molblock
from .fixtures import (
    ACETONITRILE,
    BENZENE,
    EXPECTED,
    NITROMETHANE_ANION,
    OVERLOADED,
    PYRIDINE_AROMATIC,
    PYRROLE,
)


@tagged("post_install", "-at_install")
class TestValence(BaseCase):
    def _analyse(self, molblock):
        atoms, bonds = parse_molblock(molblock)
        return valence.analyse(atoms, bonds)

    def test_fixtures_match_expected(self):
        for name, molblock in (
            ("benzene", BENZENE),
            ("acetonitrile", ACETONITRILE),
            ("nitromethane_anion", NITROMETHANE_ANION),
            ("pyrrole", PYRROLE),
            ("pyridine_aromatic", PYRIDINE_AROMATIC),
        ):
            with self.subTest(molecule=name):
                report = self._analyse(molblock)
                expected = EXPECTED[name]
                self.assertEqual(report["formula"], expected["formula"])
                self.assertAlmostEqual(report["weight"], expected["weight"], places=2)
                self.assertAlmostEqual(
                    report["monoisotopic"], expected["monoisotopic"], places=3
                )
                self.assertEqual(report["charge"], expected["charge"])
                self.assertEqual(report["rings"], expected["rings"])
                self.assertEqual(report["unsaturation"], expected["unsaturation"])
                self.assertEqual(report["rotatable_bonds"], expected["rotatable_bonds"])
                self.assertEqual(report["heavy_atoms"], expected["heavy_atoms"])
                self.assertEqual(report["aromatic_rings"], expected["aromatic_rings"])

    def test_charge_moves_the_valence(self):
        self.assertEqual(valence.implicit_hydrogens("N", 1, 4), (0, False))
        self.assertEqual(valence.implicit_hydrogens("N", 0, 4), (1, False))
        self.assertEqual(valence.implicit_hydrogens("O", -1, 1), (0, False))
        self.assertEqual(valence.implicit_hydrogens("C", 1, 3), (0, False))
        self.assertEqual(valence.implicit_hydrogens("C", 0, 3), (1, False))

    def test_exceeded_valence_refuses_to_guess(self):
        report = self._analyse(OVERLOADED)
        self.assertTrue(report["exceeded"])
        self.assertIsNone(report["weight"])
        self.assertIsNone(report["monoisotopic"])
        count, over = valence.implicit_hydrogens("C", 0, 5)
        self.assertTrue(over)
        self.assertEqual(count, 0)

    def test_ring_membership_from_bridges(self):
        atoms, bonds = parse_molblock(BENZENE)
        self.assertEqual(len(valence.ring_bonds(atoms, bonds)), 6)
        atoms, bonds = parse_molblock(ACETONITRILE)
        self.assertEqual(valence.ring_bonds(atoms, bonds), set())

    def test_aromatic_bonds_are_kekulized_on_read(self):
        atoms, bonds = parse_molblock(PYRIDINE_AROMATIC)
        self.assertEqual(
            sorted(bond["bond_order"] for bond in bonds), [1, 1, 1, 2, 2, 2]
        )
        by_idx = {atom["idx"]: atom for atom in atoms}
        for idx in by_idx:
            orders = [
                b["bond_order"] for b in bonds if idx in (b["atom_a"], b["atom_b"])
            ]
            self.assertEqual(orders.count(2), 1, by_idx[idx]["element"])

    def test_pyrrole_nitrogen_gives_its_pair_to_the_ring(self):
        atoms, bonds = parse_molblock(PYRROLE)
        aromatic = valence.aromaticity(atoms, bonds)
        self.assertEqual(aromatic["atoms"], {1, 2, 3, 4, 5})
        self.assertEqual(aromatic["donors"], {1})
        self.assertEqual(valence.hybridisation("N", [1, 1], aromatic=True), "sp2")
        report = valence.analyse(atoms, bonds)
        self.assertEqual((report["hbd"], report["hba"]), (1, 0))

    def test_huckel_rejects_what_is_not_aromatic(self):
        def ring(elements, orders, extra=(), charges=None):
            atoms = [
                {"idx": i, "element": e, "formal_charge": (charges or {}).get(i, 0)}
                for i, e in enumerate(elements, start=1)
            ]
            size = len(orders)
            bonds = [
                {
                    "atom_a": min(i, i % size + 1),
                    "atom_b": max(i, i % size + 1),
                    "bond_order": o,
                }
                for i, o in enumerate(orders, start=1)
            ] + [{"atom_a": a, "atom_b": b, "bond_order": o} for a, b, o in extra]
            return valence.aromaticity(atoms, bonds)["rings"]

        self.assertEqual(ring("CCCCC", [2, 1, 2, 1, 1]), 0)
        self.assertEqual(
            ring("CCCCC", [2, 1, 2, 1, 1], charges={5: -1}), 1
        )
        self.assertEqual(ring("CCCCCCCC", [2, 1] * 4), 0)
        self.assertEqual(
            ring("CCCCCCOO", [1, 2, 1, 1, 2, 1], [(1, 7, 2), (4, 8, 2)]), 0
        )
        self.assertEqual(
            ring("NCCCCCO", [1, 1, 2, 1, 2, 1], [(2, 7, 2)]), 1
        )

    def test_hill_order(self):
        self.assertEqual(
            valence.hill_formula({"O": 2, "H": 8, "C": 3, "N": 1, "P": 1}), "C3H8NO2P"
        )
