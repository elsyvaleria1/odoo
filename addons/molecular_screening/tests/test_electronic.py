from odoo.tests import BaseCase, TransactionCase, tagged

from ..tools import valence
from ..tools.molfile import parse_molblock
from .fixtures import (
    ACETONITRILE,
    BENZENE,
    NITROMETHANE_ANION,
    OVERLOADED,
    PYRIDINE_AROMATIC,
)

PHOSPHONATE = """methylphosphonate
  molecular_screening      2D

  5  4  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4000    0.0000    0.0000 P   0  0  0  0  0  0  0  0  0  0  0  0
    2.1000    1.2000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    2.1000   -1.2000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    1.4000    1.4000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  2  0
  2  4  1  0
  2  5  1  0
M  END
"""


@tagged("post_install", "-at_install")
class TestElectronicStructure(BaseCase):
    def _charges(self, molblock):
        atoms, bonds = parse_molblock(molblock)
        return valence.gasteiger_charges(atoms, bonds)

    def test_charge_is_conserved(self):
        # The scheme moves charge between atoms; it may not create any, so the
        # sum over the whole molecule — hydrogens included — stays at the total
        # formal charge.
        for molblock in (BENZENE, ACETONITRILE, NITROMETHANE_ANION, PHOSPHONATE):
            with self.subTest(molblock=molblock.splitlines()[0]):
                self.assertAlmostEqual(self._charges(molblock)["total"], 0.0, places=3)

    def test_benzene_carbons_are_equivalent(self):
        charges = self._charges(BENZENE)["atoms"]
        self.assertEqual(len({round(value, 4) for value in charges.values()}), 1)
        # Carbon pulls from its hydrogen, so the ring carbons come out negative
        self.assertLess(list(charges.values())[0], 0)

    def test_nitrile_nitrogen_is_the_most_negative(self):
        charges = self._charges(ACETONITRILE)["atoms"]
        atoms, _bonds = parse_molblock(ACETONITRILE)
        nitrogen = next(atom["idx"] for atom in atoms if atom["element"] == "N")
        self.assertEqual(min(charges, key=charges.get), nitrogen)

    def test_charged_oxygen_carries_the_anion(self):
        atoms, bonds = parse_molblock(NITROMETHANE_ANION)
        charges = valence.gasteiger_charges(atoms, bonds)["atoms"]
        anionic = next(atom["idx"] for atom in atoms if atom["formal_charge"] == -1)
        self.assertLess(charges[anionic], -0.4)
        self.assertEqual(min(charges, key=charges.get), anionic)

    def test_no_charges_when_valence_is_exceeded(self):
        self.assertIsNone(self._charges(OVERLOADED))

    def test_hybridisation_and_lone_pairs(self):
        self.assertEqual(valence.hybridisation("C", [1, 3]), "sp")
        self.assertEqual(valence.hybridisation("C", [1, 1, 2]), "sp2")
        self.assertEqual(valence.hybridisation("C", [1, 1, 1, 1]), "sp3")
        self.assertEqual(valence.hybridisation("C", [2, 2]), "sp")
        # Water keeps two pairs, ammonia one, and the nitrile nitrogen one
        self.assertEqual(valence.lone_pairs("O", 0, 0, 2), 2)
        self.assertEqual(valence.lone_pairs("N", 0, 0, 3), 1)
        self.assertEqual(valence.lone_pairs("N", 0, 3, 0), 1)
        self.assertEqual(valence.lone_pairs("C", 0, 4, 0), 0)

    def test_hbond_profile(self):
        atoms, bonds = parse_molblock(BENZENE)
        self.assertEqual(valence.hbond_profile(atoms, bonds), (0, 0))
        atoms, bonds = parse_molblock(ACETONITRILE)
        self.assertEqual(valence.hbond_profile(atoms, bonds), (0, 1))
        atoms, bonds = parse_molblock(NITROMETHANE_ANION)
        self.assertEqual(valence.hbond_profile(atoms, bonds), (0, 2))


@tagged("post_install", "-at_install")
class TestStructureElectronicFields(TransactionCase):
    def _structure(self, molblock):
        compound = self.env["molecular.compound"].create_from_molblock(
            molblock, vals={"name": molblock.splitlines()[0]}
        )
        return compound, compound.structure_2d_id

    def test_atoms_carry_their_own_figures(self):
        compound, structure = self._structure(BENZENE)
        self.assertEqual(structure.formula, "C6H6")
        self.assertEqual(structure.charge_method, "gasteiger-peoe-v1")
        for atom in structure.atom_ids:
            # implicit_h used to stay at zero for every atom ever stored
            self.assertEqual(atom.implicit_h, 1)
            self.assertEqual(atom.hybridisation, "sp2")
            self.assertEqual(atom.lone_pairs, 0)
            self.assertLess(atom.partial_charge, 0)
            self.assertGreater(atom.hydrogen_charge, 0)
        self.assertEqual(compound.hbd, 0)
        self.assertEqual(compound.hba, 0)
        self.assertEqual(compound.element_symbols, "C,H")

    def test_hydrogen_bonding_and_composition_reach_the_compound(self):
        compound, _structure = self._structure(ACETONITRILE)
        self.assertEqual(compound.hba, 1)
        self.assertEqual(compound.element_symbols, "C,H,N")
        self.assertAlmostEqual(compound.monoisotopic_mass, 41.02655, places=4)
        method = compound.property_ids.filtered(lambda p: p.key == "hba").method
        self.assertEqual(method, "valence-table-v1")

    def test_unparameterised_structure_declares_no_charges(self):
        _compound, structure = self._structure(OVERLOADED)
        self.assertFalse(structure.charge_method)
        self.assertTrue(all(atom.partial_charge == 0 for atom in structure.atom_ids))
        self.assertTrue(structure.atom_ids.filtered("valence_exceeded"))

    def test_aromaticity_is_stored_beside_the_kekule_orders(self):
        compound, structure = self._structure(PYRIDINE_AROMATIC)
        self.assertEqual(compound.formula, "C5H5N")
        self.assertEqual(compound.aromatic_ring_count, 1)
        self.assertTrue(all(structure.atom_ids.mapped("aromatic")))
        self.assertTrue(all(structure.bond_ids.mapped("aromatic")))
        self.assertEqual(
            sorted(structure.bond_ids.mapped("bond_order")), [1, 1, 1, 2, 2, 2]
        )
        _compound, acetonitrile = self._structure(ACETONITRILE)
        self.assertFalse(any(acetonitrile.atom_ids.mapped("aromatic")))

    def test_search_by_element(self):
        acetonitrile, _structure = self._structure(ACETONITRILE)
        benzene, _structure = self._structure(BENZENE)
        # the database may already hold the pilot set, so search only what this test made
        nitrogenous = self.env["molecular.compound"].search(
            [
                ("id", "in", (acetonitrile | benzene).ids),
                ("element_symbols", "ilike", "N"),
            ]
        )
        self.assertEqual(nitrogenous.mapped("formula"), ["C2H3N"])
