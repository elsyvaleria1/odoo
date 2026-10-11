from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools import valence
from ..tools.molfile import parse_molblock


class WizardMolecularSketch(models.TransientModel):
    _name = "wizard.molecular.sketch"
    _description = "Draw a Molecule"

    name = fields.Char(
        required=True,
        help="Name the compound will carry, e.g. CHEMBL461.",
    )
    campaign_id = fields.Many2one(comodel_name="molecular.screening.campaign")
    role = fields.Selection(
        selection=[
            ("candidate", "Candidate"),
            ("reference", "Reference"),
            ("control", "Control"),
        ],
        default="candidate",
        help="Role the compound takes in the campaign, when one is chosen.",
    )
    origin = fields.Selection(
        selection=[
            ("reference", "Reference"),
            ("similarity", "Similarity"),
            ("diversity", "Diversity"),
        ],
        help="Why the compound enters the library.",
    )
    molblock = fields.Text(
        string="Sketch",
        required=True,
    )
    molblock_3d = fields.Text(
        string="Relaxed Geometry",
        help="Filled by the editor's Keep button: the relaxed conformer, "
        "approximate geometry and not docking quality.",
    )
    summary = fields.Char(compute="_compute_summary")
    compound_id = fields.Many2one(
        comodel_name="molecular.compound",
        readonly=True,
    )

    @api.depends("molblock")
    def _compute_summary(self):
        for sketch in self:
            sketch.summary = sketch._report_line()

    def _report_line(self):
        if not self.molblock:
            return ""
        try:
            atoms, bonds = parse_molblock(self.molblock)
        except ValueError:
            return self.env._("The sketch cannot be read.")
        report = valence.analyse(atoms, bonds)
        if report["exceeded"]:
            names = ", ".join(
                f"{problem['element']}{problem['idx']}"
                for problem in report["exceeded"]
            )
            return self.env._(
                "Valence exceeded on %(atoms)s: no mass is computed.", atoms=names
            )
        return self.env._(
            "%(formula)s · %(weight)s g/mol · %(rings)s rings · %(rotatable)s rotatable bonds",
            formula=report["formula"],
            weight=f"{report['weight']:.3f}",
            rings=report["rings"],
            rotatable=report["rotatable_bonds"],
        )

    def action_save(self):
        self.check_singleton()
        if self.campaign_id and not self.role:
            raise UserError(
                self.env._("Choose the role the compound takes in the campaign.")
            )
        compound = self.env["molecular.compound"].create_from_molblock(
            self.molblock,
            vals={"name": self.name, "origin": self.origin},
            kind="2d_drawing",
            generator="molecule-editor",
        )
        if self.molblock_3d:
            self.env["molecular.structure"].create(
                {
                    "compound_id": compound.id,
                    "kind": "3d_conformer",
                    "molblock": self.molblock_3d,
                    "generator": "molecule-editor-relax",
                    "generator_ver": valence.METHOD,
                }
            )
        if self.campaign_id:
            existing = compound.role_ids.filtered(
                lambda r: r.campaign_id == self.campaign_id and r.role == self.role
            )
            if not existing:
                self.env["molecular.compound.role"].create(
                    {
                        "compound_id": compound.id,
                        "campaign_id": self.campaign_id.id,
                        "role": self.role,
                    }
                )
        self.compound_id = compound
        return {
            "type": "ir.actions.act_window",
            "res_model": "molecular.compound",
            "res_id": compound.id,
            "view_mode": "form",
        }
