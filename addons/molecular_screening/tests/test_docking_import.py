import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

MOLBLOCK = """{name}
     RDKit          3D

  1  0  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
M  END
"""


def pose(name, score, tag="minimizedAffinity"):
    return MOLBLOCK.format(name=name) + f">  <{tag}>\n{score}\n\n$$$$\n"


@tagged("post_install", "-at_install")
class TestDockingImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.campaign = cls.env["molecular.screening.campaign"].create({"name": "Test"})
        cls.compounds = {}
        for name in ("CHEMBL1", "CHEMBL2"):
            compound = cls.env["molecular.compound"].create(
                {"name": name, "identity_key": f"KEY-{name}"}
            )
            cls.env["molecular.compound.role"].create(
                {
                    "compound_id": compound.id,
                    "campaign_id": cls.campaign.id,
                    "role": "candidate",
                }
            )
            cls.env["molecular.structure"].create(
                {
                    "compound_id": compound.id,
                    "kind": "3d_conformer",
                    "molblock": MOLBLOCK.format(name=name),
                }
            )
            cls.compounds[name] = compound
        cls.target = cls.env["molecular.target"].create(
            {"name": "AHAS", "campaign_id": cls.campaign.id}
        )
        cls.env["molecular.validation.run"].create(
            {
                "target_id": cls.target.id,
                "ref_ligand": "1CS",
                "engine": "smina",
                "engine_ver": "Oct 15 2019",
                "rmsd_top": 1.84,
            }
        ).action_set_active()
        cls.campaign.action_prepare_docking_jobs()
        cls.job = cls.campaign.job_ids

    def _import(self, text, **kwargs):
        wizard = self.env["wizard.molecular.docking.import"].create(
            dict(
                {"job_id": self.job.id, "sdf_file": base64.b64encode(text.encode())},
                **kwargs,
            )
        )
        return wizard, wizard.action_import()

    def test_poses_rank_in_file_order_and_close_the_job(self):
        wizard, _action = self._import(
            pose("CHEMBL1", -7.5) + pose("CHEMBL1", -7.1) + pose("CHEMBL2", -6.2)
        )
        # The method defaults to the run that earned the gate
        self.assertEqual((wizard.engine, wizard.engine_ver), ("smina", "Oct 15 2019"))
        first = self.compounds["CHEMBL1"].result_ids.sorted("pose_rank")
        self.assertEqual(first.mapped("pose_rank"), [1, 2])
        self.assertEqual(first.mapped("score"), [-7.5, -7.1])
        self.assertEqual(
            first[0].structure_id, self.compounds["CHEMBL1"].structure_3d_id
        )
        self.assertIn("M  END", first[0].pose_molblock)
        self.assertEqual(self.job.pairs_done, 2)
        self.assertEqual(self.job.status, "ok")
        self.assertEqual(self.job.engine, "smina")

    def test_reimport_replaces_the_compound_poses(self):
        self._import(
            pose("CHEMBL1", -7.5) + pose("CHEMBL1", -7.1) + pose("CHEMBL2", -6.2)
        )
        self._import(pose("CHEMBL1", -8.0))
        results = self.compounds["CHEMBL1"].result_ids
        self.assertEqual(results.mapped("score"), [-8.0])
        # A compound absent from the second file keeps its poses
        self.assertEqual(self.compounds["CHEMBL2"].result_ids.mapped("score"), [-6.2])

    def test_pose_finds_a_structure_merged_into_another_name(self):
        # The pilot exported imidacloprid's control as CHEMBL406819: one compound
        # under the reference's name, whose 3D structure keeps the docked title
        compound = self.compounds["CHEMBL2"]
        compound.structure_3d_id.molblock = MOLBLOCK.format(name="CHEMBL406819")
        self._import(pose("CHEMBL406819", -6.9))
        self.assertEqual(compound.result_ids.score, -6.9)

    def test_other_score_tag(self):
        self._import(pose("CHEMBL1", -9.1, tag="CNNaffinity"), score_tag="CNNaffinity")
        self.assertEqual(self.compounds["CHEMBL1"].result_ids.score, -9.1)

    def test_unknown_compound_imports_nothing(self):
        with self.assertRaises(UserError):
            self._import(pose("CHEMBL1", -7.5) + pose("NOT-IN-CAMPAIGN", -6.0))
        self.assertFalse(self.job.result_ids)
        self.assertEqual(self.job.status, "pending")

    def test_bad_files(self):
        with self.assertRaises(UserError):
            self._import("nothing here")
        with self.assertRaises(UserError):
            self._import(pose("CHEMBL1", "strong"))

    def test_blocked_job_refuses_import(self):
        self.job.status = "blocked"
        with self.assertRaises(UserError):
            self._import(pose("CHEMBL1", -7.5))
