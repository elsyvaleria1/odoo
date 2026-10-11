from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestValidationGate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.campaign = cls.env["molecular.screening.campaign"].create({"name": "Test"})
        cls.compound = cls.env["molecular.compound"].create(
            {"name": "CHEMBL1", "identity_key": "SH1-TEST"}
        )
        cls.env["molecular.compound.role"].create(
            {
                "compound_id": cls.compound.id,
                "campaign_id": cls.campaign.id,
                "role": "candidate",
            }
        )
        cls.structure = cls.env["molecular.structure"].create(
            {
                "compound_id": cls.compound.id,
                "kind": "3d_conformer",
                "molblock": "x\n\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\n"
                "    0.0000    0.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "M  END\n",
            }
        )

    def _target(self, name):
        return self.env["molecular.target"].create(
            {"name": name, "campaign_id": self.campaign.id}
        )

    def _run(self, target, rmsd_top, poses=(), **kwargs):
        return self.env["molecular.validation.run"].create(
            dict(
                {
                    "target_id": target.id,
                    "ref_ligand": "AZO",
                    "engine": "smina",
                    "engine_ver": "Oct 15 2019",
                    "rmsd_top": rmsd_top,
                    "pose_ids": [
                        Command.create(
                            {"rank": rank, "affinity": affinity, "rmsd": rmsd}
                        )
                        for rank, affinity, rmsd in poses
                    ],
                },
                **kwargs,
            )
        )

    def test_gate_judges_top_pose(self):
        target = self._target("EPSPS_wt")
        self.assertEqual(target.validation_state, "pending")
        run = self._run(target, 0.75, [(1, -5.83, 0.75), (2, -5.49, 0.61)])
        self.assertTrue(run.passed)
        self.assertEqual(run.best_pose_rank, 2)
        self.assertEqual(target.validation_state, "pending")
        run.action_set_active()
        self.assertEqual(target.validation_state, "pass")
        self.assertAlmostEqual(target.rmsd_top, 0.75)

    def test_failed_run_stays_on_file_beside_the_retry(self):
        target = self._target("bc1_Qo")
        failed = self._run(target, 2.91, [(1, -10.54, 2.91), (7, -8.74, 0.97)])
        failed.action_set_active()
        self.assertEqual(target.validation_state, "fail")
        self.assertAlmostEqual(failed.rmsd_best, 0.97)
        retry = self._run(target, 1.90, scoring="vinardo", autobox_padding=4)
        self.assertEqual(target.validation_run_count, 2)
        self.assertEqual(target.active_validation_id, failed)
        target.action_activate_latest_run()
        self.assertEqual(target.active_validation_id, retry)
        self.assertEqual(target.validation_state, "pass")
        self.assertAlmostEqual(failed.rmsd_top, 2.91)

    def test_one_failing_target_does_not_block_the_others(self):
        passing = self._target("EPSPS_wt")
        self._run(passing, 0.75).action_set_active()
        failing = self._target("bc1_Qo")
        self._run(failing, 2.91).action_set_active()
        self.campaign.action_prepare_docking_jobs()
        jobs = {job.target_id.name: job for job in self.campaign.job_ids}
        self.assertEqual(jobs["EPSPS_wt"].status, "pending")
        self.assertEqual(jobs["bc1_Qo"].status, "blocked")
        self.assertEqual(jobs["EPSPS_wt"].pairs_expected, 1)

    def test_blocked_job_refuses_results_and_running(self):
        target = self._target("bc1_Qo")
        self._run(target, 2.91).action_set_active()
        self.campaign.action_prepare_docking_jobs()
        job = self.campaign.job_ids
        with self.assertRaises(ValidationError):
            job.status = "running"
        with self.assertRaises(ValidationError):
            self.env["molecular.docking.result"].create(
                {"job_id": job.id, "structure_id": self.structure.id, "score": -7.0}
            )

    def test_results_land_on_a_passing_job(self):
        target = self._target("EPSPS_wt")
        self._run(target, 0.75).action_set_active()
        self.campaign.action_prepare_docking_jobs()
        job = self.campaign.job_ids
        job.status = "running"
        result = self.env["molecular.docking.result"].create(
            {
                "job_id": job.id,
                "structure_id": self.structure.id,
                "score": -7.0,
                "pose_rank": 1,
            }
        )
        self.assertEqual(result.compound_id, self.compound)
        self.assertEqual(result.campaign_id, self.campaign)
        self.assertEqual(job.pairs_done, 1)
        self.assertEqual(self.compound.result_ids, result)

    def test_gate_reread_unblocks_a_rescued_target(self):
        target = self._target("bc1_Qo")
        self._run(target, 2.91).action_set_active()
        self.campaign.action_prepare_docking_jobs()
        job = self.campaign.job_ids
        self.assertEqual(job.status, "blocked")
        self._run(target, 1.90).action_set_active()
        job.action_refresh_gate()
        self.assertEqual(job.status, "pending")
