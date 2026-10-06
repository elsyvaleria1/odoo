from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import frozendict

from ..tools import valence
from ..tools.molfile import parse_molblock


class MolecularStructure(models.Model):
    _name = "molecular.structure"
    # Chemical identity and its geometries are shared across companies.
    _access_anchors = frozendict({"company": ""})
    _description = "Molecular Structure"
    _order = "compound_id, create_date desc"
    _rec_name = "display_name"

    compound_id = fields.Many2one(
        comodel_name="molecular.compound",
        index=True,
        required=True,
        ondelete="cascade",
    )
    kind = fields.Selection(
        selection=[
            ("2d_drawing", "2D Drawing"),
            ("3d_conformer", "3D Conformer"),
            ("protonated", "Protonated"),
        ],
        required=True,
    )
    ph = fields.Float(
        string="pH",
        digits=(4, 2),
        help="Only for protonated structures.",
    )
    molblock = fields.Text(
        required=True,
        help="V2000 connection table: the source of truth.",
    )
    svg = fields.Text(
        string="2D Drawing",
        help="Optional rendering of the structure.",
    )
    generator = fields.Char(help="What produced the geometry, e.g. rdkit-etkdg.")
    generator_ver = fields.Char(string="Generator Version")
    atom_ids = fields.One2many(
        comodel_name="molecular.structure.atom",
        inverse_name="structure_id",
        string="Atoms",
    )
    bond_ids = fields.One2many(
        comodel_name="molecular.structure.bond",
        inverse_name="structure_id",
        string="Bonds",
    )
    atom_count = fields.Integer(
        compute="_compute_counts",
        store=True,
    )
    bond_count = fields.Integer(
        compute="_compute_counts",
        store=True,
    )
    heavy_atom_count = fields.Integer(
        compute="_compute_counts",
        store=True,
        help="Atoms other than hydrogen in the connection table.",
    )
    formula = fields.Char(
        readonly=True,
        help="Hill formula of this connection table.",
    )
    net_charge = fields.Integer(readonly=True)
    charge_method = fields.Char(
        readonly=True,
        help="Scheme that produced the partial charges, or empty when no "
        "parameter set covers every element in the structure.",
    )

    @api.depends("compound_id.display_name", "kind")
    def _compute_display_name(self):
        kinds = dict(self._fields["kind"].selection)
        for structure in self:
            structure.display_name = "{} — {}".format(
                structure.compound_id.display_name, kinds.get(structure.kind, "")
            )

    @api.depends("atom_ids.element", "bond_ids")
    def _compute_counts(self):
        for structure in self:
            structure.atom_count = len(structure.atom_ids)
            structure.bond_count = len(structure.bond_ids)
            structure.heavy_atom_count = len(
                structure.atom_ids.filtered(lambda atom: atom.element != "H")
            )

    @api.constrains("kind", "ph")
    def _check_ph(self):
        for structure in self:
            if structure.ph and structure.kind != "protonated":
                raise ValidationError(
                    self.env._("Only a protonated structure carries a pH.")
                )

    def action_explode_molblock(self):
        """Replace the atom and bond tables with the molblock's own connectivity.

        Each atom also gets what the valence table can say about it on its own:
        how many hydrogens complete it, whether it is aromatic, how it is
        hybridised, how many lone pairs it keeps, and — when every element is
        parameterised — its partial charge.
        """
        for structure in self:
            try:
                atoms, bonds = parse_molblock(structure.molblock)
            except ValueError as err:
                raise ValidationError(
                    self.env._(
                        "Structure %(name)s: %(error)s",
                        name=structure.display_name,
                        error=str(err),
                    )
                ) from None
            report = valence.analyse(atoms, bonds)
            charges = valence.gasteiger_charges(atoms, bonds)
            aromatic = valence.aromaticity(atoms, bonds)
            for position, bond in enumerate(bonds):
                bond["aromatic"] = position in aromatic["bonds"]
            adjacency = {atom["idx"]: [] for atom in atoms}
            for bond in bonds:
                adjacency[bond["atom_a"]].append(bond["bond_order"])
                adjacency[bond["atom_b"]].append(bond["bond_order"])

            atom_vals = []
            for atom in atoms:
                orders = adjacency[atom["idx"]]
                charge = atom.get("formal_charge") or 0
                used = sum(orders)
                count, exceeded = valence.implicit_hydrogens(
                    atom["element"], charge, used
                )
                atom_vals.append(
                    dict(
                        atom,
                        implicit_h=0 if exceeded else count,
                        valence_exceeded=exceeded,
                        aromatic=atom["idx"] in aromatic["atoms"],
                        hybridisation=valence.hybridisation(
                            atom["element"], orders, atom["idx"] in aromatic["atoms"]
                        ),
                        lone_pairs=0
                        if exceeded
                        else valence.lone_pairs(atom["element"], charge, used, count),
                        partial_charge=charges["atoms"][atom["idx"]]
                        if charges
                        else 0.0,
                        hydrogen_charge=charges["hydrogens"][atom["idx"]]
                        if charges
                        else 0.0,
                    )
                )

            structure.atom_ids.unlink()
            structure.bond_ids.unlink()
            structure.write(
                {
                    "atom_ids": [fields.Command.create(atom) for atom in atom_vals],
                    "bond_ids": [fields.Command.create(bond) for bond in bonds],
                    "formula": report["formula"],
                    "net_charge": report["charge"],
                    # An unparameterised element leaves this empty rather than
                    # letting a column of zeros pass for computed charges.
                    "charge_method": valence.PEOE_METHOD if charges else False,
                }
            )

    @api.model_create_multi
    def create(self, vals_list):
        structures = super().create(vals_list)
        structures.action_explode_molblock()
        return structures


class MolecularStructureAtom(models.Model):
    _name = "molecular.structure.atom"
    # Chemical identity and its geometries are shared across companies.
    _access_anchors = frozendict({"company": ""})
    _description = "Structure Atom"
    _order = "structure_id, idx"

    structure_id = fields.Many2one(
        comodel_name="molecular.structure",
        index=True,
        required=True,
        ondelete="cascade",
    )
    idx = fields.Integer(
        string="Index",
        required=True,
        help="1-based, as in the molblock.",
    )
    element = fields.Char(required=True)
    x = fields.Float(digits=(16, 4))
    y = fields.Float(digits=(16, 4))
    z = fields.Float(digits=(16, 4))
    formal_charge = fields.Integer(default=0)
    implicit_h = fields.Integer(
        string="Implicit H",
        default=0,
    )
    valence_exceeded = fields.Boolean(
        help="The valence table has no room for this atom's bonds, so its derived "
        "figures are left unset instead of guessed."
    )
    aromatic = fields.Boolean(help="Part of a ring that satisfies Hückel's 4n+2 rule.")
    hybridisation = fields.Selection(
        selection=[("sp", "sp"), ("sp2", "sp²"), ("sp3", "sp³")],
        help="Read from the bond orders around the atom and its aromaticity.",
    )
    lone_pairs = fields.Integer(help="Non-bonding electron pairs left on the atom.")
    partial_charge = fields.Float(
        digits=(16, 4),
        help="Empirical Gasteiger charge of the atom itself, hydrogens excluded.",
    )
    hydrogen_charge = fields.Float(
        string="Charge on H",
        digits=(16, 4),
        help="Sum of the charges of the hydrogens completing this atom, which is "
        "what a docking engine merges into it for a nonpolar hydrogen.",
    )

    _idx_uniq = models.Constraint(
        "unique(structure_id, idx)", "Two atoms cannot share an index."
    )


class MolecularStructureBond(models.Model):
    _name = "molecular.structure.bond"
    # Chemical identity and its geometries are shared across companies.
    _access_anchors = frozendict({"company": ""})
    _description = "Structure Bond"
    _order = "structure_id, atom_a, atom_b"

    structure_id = fields.Many2one(
        comodel_name="molecular.structure",
        index=True,
        required=True,
        ondelete="cascade",
    )
    atom_a = fields.Integer(required=True)
    atom_b = fields.Integer(required=True)
    bond_order = fields.Integer(
        default=1,
        required=True,
    )
    aromatic = fields.Boolean(
        default=False,
        help="Part of a ring that satisfies Hückel's 4n+2 rule.",
    )
    stereo = fields.Integer(
        default=0,
        help="0 plain, 1 wedge, 6 hash, as in the molblock.",
    )

    _bond_uniq = models.Constraint(
        "unique(structure_id, atom_a, atom_b)", "This bond is already recorded."
    )
    # Normalising the order is what stops one bond entering twice reversed.
    _atom_order = models.Constraint(
        "check(atom_a < atom_b)",
        "A bond must be stored with its lower atom index first.",
    )
    _bond_order_range = models.Constraint(
        "check(bond_order between 1 and 3)", "A bond order runs from 1 to 3."
    )
