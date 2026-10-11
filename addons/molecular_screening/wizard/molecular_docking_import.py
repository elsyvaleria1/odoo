import base64
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools.sdf_parser import parse_sdf


class WizardMolecularDockingImport(models.TransientModel):
    _name = "wizard.molecular.docking.import"
    _description = "Import Docking Results"

    job_id = fields.Many2one(
        comodel_name="molecular.docking.job",
        required=True,
    )
    sdf_file = fields.Binary(
        string="Poses (SDF)",
        required=True,
    )
    sdf_filename = fields.Char()
    engine = fields.Char(
        compute="_compute_engine",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
        help="Docking engine that produced the poses, e.g. smina.",
    )
    engine_ver = fields.Char(
        string="Engine Version",
        compute="_compute_engine",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    score_tag = fields.Char(
        default="minimizedAffinity",
        required=True,
        help="SD data tag holding the score in kcal/mol: minimizedAffinity for "
        "smina and GNINA.",
    )

    @api.depends("job_id")
    def _compute_engine(self):
        for wizard in self:
            run = wizard.job_id.target_id.active_validation_id
            wizard.engine = wizard.job_id.engine or run.engine
            wizard.engine_ver = wizard.job_id.engine_ver or run.engine_ver

    def _match_structures(self, names):
        compounds = self.job_id.campaign_id.role_ids.compound_id
        by_title = defaultdict(list)
        for structure in compounds.structure_ids.filtered(
            lambda s: s.kind in ("3d_conformer", "protonated")
        ):
            by_title[structure.molblock.split("\n", 1)[0].strip()].append(structure)
        by_name = defaultdict(list)
        for compound in compounds.filtered("structure_3d_id"):
            by_name[compound.name].append(compound.structure_3d_id)
        problems = []
        structures = {}
        for name in sorted(names):
            matches = by_title.get(name) or by_name.get(name, [])
            if len(matches) == 1:
                structures[name] = matches[0]
            else:
                problems.append(
                    self.env._(
                        "%(name)s: %(count)s 3D structures in the campaign",
                        name=name,
                        count=len(matches),
                    )
                )
        if problems:
            raise UserError(
                self.env._(
                    "Nothing was imported:\n%(problems)s", problems="\n".join(problems)
                )
            )
        return structures

    def action_import(self):
        self.check_singleton()
        job = self.job_id
        if job.status == "blocked":
            raise UserError(
                self.env._(
                    "Job %(job)s is blocked: its target has not passed the redocking gate.",
                    job=job.display_name,
                )
            )
        try:
            text = base64.b64decode(self.sdf_file).decode("utf-8")
        except UnicodeDecodeError:
            raise UserError(
                self.env._("The SDF file is not valid UTF-8 text.")
            ) from None
        records = parse_sdf(text)
        if not records:
            raise UserError(self.env._("No poses were found in the SDF file."))
        structures = self._match_structures({record["name"] for record in records})

        rank = defaultdict(int)
        vals_list = []
        for record in records:
            raw = record["tags"].get(self.score_tag)
            try:
                score = float(raw)
            except TypeError, ValueError:
                raise UserError(
                    self.env._(
                        "%(name)s: tag %(tag)s is missing or not a number.",
                        name=record["name"],
                        tag=self.score_tag,
                    )
                ) from None
            rank[record["name"]] += 1
            vals_list.append(
                {
                    "job_id": job.id,
                    "structure_id": structures[record["name"]].id,
                    "score": score,
                    "pose_rank": rank[record["name"]],
                    "pose_molblock": record["molblock"],
                }
            )
        job.result_ids.filtered(
            lambda result: result.structure_id.id in {s.id for s in structures.values()}
        ).unlink()
        self.env["molecular.docking.result"].create(vals_list)
        job.write(
            {
                "engine": self.engine,
                "engine_ver": self.engine_ver,
                "status": "ok",
                "finished_at": fields.Datetime.now(),
                "error_msg": False,
            }
        )
