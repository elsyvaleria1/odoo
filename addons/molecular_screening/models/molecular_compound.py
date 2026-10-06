from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict

from ..tools import valence
from ..tools.chemistry import compute_identity
from ..tools.molfile import parse_molblock

# Properties promoted to stored fields because the list and kanban views sort
# and filter on them. Each one keeps its provenance in molecular.compound.property.
PROMOTED_PROPERTIES = {
    "mw": "molecular_weight",
    "monoisotopic_mass": "monoisotopic_mass",
    "logp": "logp",
    "tpsa": "tpsa",
    "rotatable_bonds": "rotatable_bonds",
    "hbd": "hbd",
    "hba": "hba",
    "rings": "ring_count",
    "aromatic_rings": "aromatic_ring_count",
}


class MolecularCompoundTag(models.Model):
    _name = "molecular.compound.tag"
    # Chemical identity and its geometries are shared across companies.
    _access_anchors = frozendict({"company": ""})
    _description = "Molecular Compound Class"

    name = fields.Char(required=True)
    color = fields.Integer()

    _name_uniq = models.Constraint("unique(name)", "This class already exists.")


class MolecularCompound(models.Model):
    _name = "molecular.compound"
    # Chemical identity and its geometries are shared across companies.
    _access_anchors = frozendict({"company": ""})
    _description = "Molecular Compound"
    _order = "name, identity_key"
    _rec_name = "display_name"

    name = fields.Char(help="Common or catalogue name, e.g. CHEMBL461 or glyphosate.")
    identity_key = fields.Char(
        index=True,
        copy=False,
        required=True,
        help="Deduplication key: the InChIKey when a toolkit produced one, "
        "otherwise a hash of the connection table.",
    )
    inchikey = fields.Char(
        size=27,
        index=True,
        copy=False,
    )
    identity_method = fields.Char(
        string="Identity Method",
        help="How identity_key was obtained, e.g. rdkit-2026.03.6.",
    )
    smiles_canon = fields.Char(string="Canonical SMILES")
    origin = fields.Selection(
        selection=[
            ("reference", "Reference"),
            ("similarity", "Similarity"),
            ("diversity", "Diversity"),
        ],
        help="Why the compound entered the library in the first place.",
    )
    formula = fields.Char(index=True)
    element_symbols = fields.Char(
        string="Elements",
        index=True,
        readonly=True,
        help="Comma-separated element list, so a search can ask for the "
        "compounds that carry bromine without parsing the formula.",
    )
    formal_charge = fields.Integer()
    tag_ids = fields.Many2many(
        comodel_name="molecular.compound.tag",
        string="Classes",
    )
    role_ids = fields.One2many(
        comodel_name="molecular.compound.role",
        inverse_name="compound_id",
        string="Roles",
    )
    campaign_ids = fields.Many2many(
        comodel_name="molecular.screening.campaign",
        string="Campaigns",
        compute="_compute_campaign_ids",
        search="_search_campaign_ids",
    )
    property_ids = fields.One2many(
        comodel_name="molecular.compound.property",
        inverse_name="compound_id",
        string="Properties",
    )
    structure_ids = fields.One2many(
        comodel_name="molecular.structure",
        inverse_name="compound_id",
        string="Structures",
    )
    # Stored so that a change to a structure can find its way back to the
    # compound: an unstored computed link is not searchable, and the related
    # fields below would then go stale when a structure is edited.
    structure_2d_id = fields.Many2one(
        comodel_name="molecular.structure",
        compute="_compute_preferred_structures",
        store=True,
    )
    structure_3d_id = fields.Many2one(
        comodel_name="molecular.structure",
        compute="_compute_preferred_structures",
        store=True,
    )
    structure_svg = fields.Text(
        related="structure_2d_id.svg",
        string="2D Drawing",
        readonly=True,
    )
    molblock_3d = fields.Text(
        related="structure_3d_id.molblock",
        string="3D Structure",
        readonly=True,
    )
    molecular_weight = fields.Float(
        digits=(16, 3),
        compute="_compute_properties",
        store=True,
    )
    monoisotopic_mass = fields.Float(
        digits=(16, 5),
        compute="_compute_properties",
        store=True,
    )
    logp = fields.Float(
        string="logP",
        digits=(16, 3),
        compute="_compute_properties",
        store=True,
    )
    tpsa = fields.Float(
        string="TPSA",
        digits=(16, 2),
        compute="_compute_properties",
        store=True,
    )
    rotatable_bonds = fields.Integer(
        compute="_compute_properties",
        store=True,
    )
    hbd = fields.Integer(
        string="H-Bond Donors",
        compute="_compute_properties",
        store=True,
    )
    hba = fields.Integer(
        string="H-Bond Acceptors",
        compute="_compute_properties",
        store=True,
    )
    ring_count = fields.Integer(
        string="Rings",
        compute="_compute_properties",
        store=True,
    )
    aromatic_ring_count = fields.Integer(
        string="Aromatic Rings",
        compute="_compute_properties",
        store=True,
    )
    result_ids = fields.One2many(
        comodel_name="molecular.docking.result",
        inverse_name="compound_id",
        string="Docking Results",
        readonly=True,
    )

    _identity_key_uniq = models.Constraint(
        "unique(identity_key)",
        "This compound is already in the library under the same identity key.",
    )

    @api.depends("name", "identity_key")
    def _compute_display_name(self):
        for compound in self:
            compound.display_name = compound.name or compound.identity_key

    @api.depends("role_ids.campaign_id")
    def _compute_campaign_ids(self):
        for compound in self:
            compound.campaign_ids = compound.role_ids.campaign_id

    def _search_campaign_ids(self, operator, value):
        return [("role_ids.campaign_id", operator, value)]

    @api.depends("structure_ids.kind", "structure_ids.create_date")
    def _compute_preferred_structures(self):
        for compound in self:
            structures = compound.structure_ids.sorted(
                lambda structure: (structure.create_date, structure.id), reverse=True
            )
            compound.structure_2d_id = structures.filtered(
                lambda s: s.kind == "2d_drawing"
            )[:1]
            compound.structure_3d_id = structures.filtered(
                lambda s: s.kind in ("3d_conformer", "protonated")
            )[:1]

    @api.depends("property_ids.key", "property_ids.value_num")
    def _compute_properties(self):
        for compound in self:
            for key, field_name in PROMOTED_PROPERTIES.items():
                compound[field_name] = compound._get_property(key).value_num or 0.0

    def _get_property(self, key):
        """Return the property record of ``key`` that governs the stored field.

        Several methods may have computed the same key; the most recent one wins.

        :param str key: property key, e.g. ``mw``
        :rtype: odoo.models.Model
        """
        self.check_singleton()
        candidates = self.property_ids.filtered(lambda p: p.key == key)
        return candidates.sorted(
            lambda prop: (prop.computed_at, prop.id), reverse=True
        )[:1]

    @api.model
    def create_from_molblock(
        self, molblock, vals=None, kind="2d_drawing", generator=None
    ):
        """Create or complete a compound from a drawn connection table.

        The structure is stored as given and the derived figures are recomputed
        here rather than trusted from the client, so what the database holds is
        always what tools/valence.py says about the molblock it holds.

        :param str molblock: V2000 connection table
        :param dict vals: extra compound values, e.g. name or origin
        :param str kind: structure kind to store the geometry under
        :param str generator: what drew it, recorded on the structure
        :rtype: odoo.models.Model
        """
        try:
            atoms, bonds = parse_molblock(molblock)
        except ValueError as err:
            raise UserError(
                self.env._("The drawing could not be read: %(error)s", error=str(err))
            ) from None
        if not atoms:
            raise UserError(self.env._("Draw at least one atom before saving."))
        unknown = {atom["element"] for atom in atoms} - set(valence.WEIGHTS)
        if unknown:
            raise UserError(
                self.env._(
                    "Unsupported elements: %(elements)s",
                    elements=", ".join(sorted(unknown)),
                )
            )

        identity = compute_identity(molblock=molblock, atoms=atoms, bonds=bonds)
        report = valence.analyse(atoms, bonds)
        compound = self.search(
            [("identity_key", "=", identity["identity_key"])], limit=1
        )
        compound_vals = dict(vals or {})
        compound_vals.update(
            identity_key=identity["identity_key"],
            inchikey=identity["inchikey"],
            identity_method=identity["method"],
            smiles_canon=identity["smiles_canon"],
            formula=report["formula"],
            element_symbols=",".join(sorted(report["counts"])),
            formal_charge=report["charge"],
        )
        if compound:
            compound.write(
                {
                    key: value
                    for key, value in compound_vals.items()
                    if key != "name" or not compound.name
                }
            )
        else:
            compound = self.create(compound_vals)

        self.env["molecular.structure"].create(
            {
                "compound_id": compound.id,
                "kind": kind,
                "molblock": molblock,
                "generator": generator or "molecule-editor",
                "generator_ver": valence.METHOD,
            }
        )
        compound._store_valence_properties(report)
        return compound

    def _store_valence_properties(self, report):
        """Record the figures the valence table can defend, and only those."""
        self.check_singleton()
        numeric = {
            "mw": report["weight"],
            "monoisotopic_mass": report["monoisotopic"],
            "rotatable_bonds": report["rotatable_bonds"],
            "rings": report["rings"],
            "aromatic_rings": report["aromatic_rings"],
            "heavy_atoms": report["heavy_atoms"],
            "unsaturation": report["unsaturation"],
            "hbd": report["hbd"],
            "hba": report["hba"],
        }
        for key, value in numeric.items():
            # A molecule whose valence is exceeded has no defensible mass, so
            # that row is left out instead of carrying a zero.
            if value is not None:
                self.set_property(key, valence.METHOD, value_num=value)

    def action_open_sketch(self):
        """Open the drawing editor on this compound's 2D structure."""
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "molecular_screening.molecular_sketch_action"
        )
        action["context"] = {
            "default_name": self.name,
            "default_origin": self.origin,
            "default_molblock": self.structure_2d_id.molblock
            or self.structure_3d_id.molblock,
        }
        return action

    def action_recompute_properties(self):
        """Recompute the valence-derived properties from the stored structure."""
        for compound in self:
            structure = compound.structure_2d_id or compound.structure_3d_id
            if not structure:
                continue
            atoms, bonds = parse_molblock(structure.molblock)
            report = valence.analyse(atoms, bonds)
            compound.write(
                {
                    "formula": report["formula"],
                    "element_symbols": ",".join(sorted(report["counts"])),
                    "formal_charge": report["charge"],
                }
            )
            compound._store_valence_properties(report)

    def set_property(self, key, method, value_num=None, value_bool=None):
        """Record a property value together with the method that produced it.

        :param str key: property key
        :param str method: provenance, e.g. ``rdkit-2026.03.6`` or ``deterministic``
        :param float value_num: numeric value, when the property is numeric
        :param bool value_bool: boolean value, when the property is a flag
        :rtype: odoo.models.Model
        """
        self.check_singleton()
        vals = {"value_num": value_num, "value_bool": value_bool}
        existing = self.property_ids.filtered(
            lambda p: p.key == key and p.method == method
        )
        if existing:
            existing.write(dict(vals, computed_at=fields.Datetime.now()))
            return existing
        return self.env["molecular.compound.property"].create(
            dict(vals, compound_id=self.id, key=key, method=method)
        )


class MolecularCompoundRole(models.Model):
    _name = "molecular.compound.role"
    _access_anchors = frozendict({"company": "campaign_id.company_id"})
    _description = "Compound Role in a Campaign"
    _order = "campaign_id, role, compound_id"

    compound_id = fields.Many2one(
        comodel_name="molecular.compound",
        index=True,
        required=True,
        ondelete="cascade",
    )
    campaign_id = fields.Many2one(
        comodel_name="molecular.screening.campaign",
        index=True,
        required=True,
        ondelete="cascade",
    )
    role = fields.Selection(
        selection=[
            ("reference", "Reference"),
            ("candidate", "Candidate"),
            ("control", "Control"),
        ],
        required=True,
    )
    note = fields.Char(help="Why the compound holds this role, e.g. Tanimoto 0.323.")

    _role_uniq = models.Constraint(
        "unique(compound_id, campaign_id, role)",
        "The compound already holds this role in the campaign.",
    )


class MolecularCompoundProperty(models.Model):
    _name = "molecular.compound.property"
    # Chemical identity and its geometries are shared across companies.
    _access_anchors = frozendict({"company": ""})
    _description = "Compound Property with Provenance"
    _order = "compound_id, key, computed_at desc"

    compound_id = fields.Many2one(
        comodel_name="molecular.compound",
        index=True,
        required=True,
        ondelete="cascade",
    )
    key = fields.Char(required=True)
    # Six decimals because a monoisotopic mass needs five and this column is the
    # only carrier: rounding here silently truncated the promoted field.
    value_num = fields.Float(digits=(16, 6))
    value_bool = fields.Boolean()
    method = fields.Char(
        required=True,
        help="What computed the value: a toolkit and version, an internal rule, "
        "or 'deterministic' when it follows from the formula alone.",
    )
    computed_at = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )

    _key_method_uniq = models.Constraint(
        "unique(compound_id, key, method)",
        "This property was already recorded for the compound with the same method.",
    )
