from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .fixtures import ACETONITRILE
from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestMolecularScreeningAccessMatrix(AccessMatrixCase):
    personas = {
        "internal": Persona("base.group_user"),
        "user_a": Persona("molecular_screening.group_molecular_screening_user"),
        "user_b": Persona(
            "molecular_screening.group_molecular_screening_user", company="b"
        ),
        "manager_a": Persona("molecular_screening.group_molecular_screening_manager"),
        "manager_b": Persona(
            "molecular_screening.group_molecular_screening_manager", company="b"
        ),
    }
    cells = (
        Cell(
            "molecular.compound",
            "compound",
            user_a="rwc",
            user_b="rwc",
            manager_a="rwcd",
            manager_b="rwcd",
        ),
        Cell(
            "molecular.compound.tag",
            "tag",
            user_a="rwc",
            user_b="rwc",
            manager_a="rwcd",
            manager_b="rwcd",
        ),
        Cell(
            "molecular.compound.property",
            "property",
            user_a="rwc",
            user_b="rwc",
            manager_a="rwcd",
            manager_b="rwcd",
        ),
        Cell(
            "molecular.structure",
            "structure",
            user_a="rwc",
            user_b="rwc",
            manager_a="rwcd",
            manager_b="rwcd",
        ),
        Cell(
            "molecular.structure.atom",
            "atom",
            user_a="rwcd",
            user_b="rwcd",
            manager_a="rwcd",
            manager_b="rwcd",
        ),
        Cell(
            "molecular.structure.bond",
            "bond",
            user_a="rwcd",
            user_b="rwcd",
            manager_a="rwcd",
            manager_b="rwcd",
        ),
        Cell(
            "molecular.screening.campaign", "campaign_a", user_a="rwc", manager_a="rwcd"
        ),
        Cell(
            "molecular.screening.campaign", "campaign_b", user_b="rwc", manager_b="rwcd"
        ),
        Cell("molecular.target", "target_a", user_a="rwc", manager_a="rwcd"),
        Cell("molecular.target", "target_b", user_b="rwc", manager_b="rwcd"),
        Cell("molecular.compound.role", "role_a", user_a="rwc", manager_a="rwcd"),
        Cell("molecular.compound.role", "role_b", user_b="rwc", manager_b="rwcd"),
        Cell("molecular.validation.run", "run_a", user_a="rwc", manager_a="rwcd"),
        Cell("molecular.validation.run", "run_b", user_b="rwc", manager_b="rwcd"),
        Cell("molecular.validation.pose", "pose_a", user_a="rwc", manager_a="rwcd"),
        Cell("molecular.validation.pose", "pose_b", user_b="rwc", manager_b="rwcd"),
        Cell("molecular.docking.job", "job_a", user_a="rwc", manager_a="rwcd"),
        Cell("molecular.docking.job", "job_b", user_b="rwc", manager_b="rwcd"),
        Cell("molecular.docking.result", "result_a", user_a="rwc", manager_a="rwcd"),
        Cell("molecular.docking.result", "result_b", user_b="rwc", manager_b="rwcd"),
    )

    @classmethod
    def build(cls):
        env = cls.env
        compound = env["molecular.compound"].create_from_molblock(ACETONITRILE)
        structure = compound.structure_ids
        structure.action_explode_molblock()
        records = {
            "compound": compound,
            "tag": env["molecular.compound.tag"].create({"name": "Matrix class"}),
            "property": compound.property_ids[:1],
            "structure": structure,
            "atom": structure.atom_ids[:1],
            "bond": structure.bond_ids[:1],
        }
        for key, company in cls.companies.items():
            campaign = env["molecular.screening.campaign"].create(
                {"name": key, "company_id": company.id}
            )
            target = env["molecular.target"].create(
                {"name": key, "campaign_id": campaign.id}
            )
            role = env["molecular.compound.role"].create(
                {
                    "compound_id": compound.id,
                    "campaign_id": campaign.id,
                    "role": "candidate",
                }
            )
            run = env["molecular.validation.run"].create(
                {
                    "target_id": target.id,
                    "ref_ligand": "REF",
                    "engine": "test",
                    "engine_ver": "1",
                    "rmsd_top": 0.5,
                    "pose_ids": [Command.create({"rank": 1, "rmsd": 0.5})],
                }
            )
            run.action_set_active()
            campaign.action_prepare_docking_jobs()
            job = campaign.job_ids
            result = env["molecular.docking.result"].create(
                {"job_id": job.id, "structure_id": structure.id, "score": -1}
            )
            records.update(
                {
                    f"{name}_{key}": record
                    for name, record in {
                        "campaign": campaign,
                        "target": target,
                        "role": role,
                        "run": run,
                        "pose": run.pose_ids,
                        "job": job,
                        "result": result,
                    }.items()
                }
            )
        return records

    def test_shared_compound_does_not_disclose_other_company_results(self):
        compound = self.records["compound"].with_env(self._principal("user_a"))
        self.assertEqual(compound.campaign_ids, self.records["campaign_a"])
        self.assertEqual(compound.result_ids, self.records["result_a"])
        self.assertEqual(compound.role_ids, self.records["role_a"])

    def test_cannot_create_a_target_in_another_company(self):
        with self.assertRaises(AccessError):
            self._principal("user_a")["molecular.target"].create(
                {
                    "name": "Foreign",
                    "campaign_id": self.records["campaign_b"].id,
                }
            )

    def test_sketch_can_save_in_own_company_but_not_another(self):
        env = self._principal("user_a")
        sketch = env["wizard.molecular.sketch"].create(
            {
                "name": "Drawn",
                "molblock": ACETONITRILE,
                "campaign_id": self.records["campaign_a"].id,
                "role": "reference",
            }
        )
        sketch.action_save()
        self.assertEqual(sketch.compound_id, self.records["compound"])
        with self.assertRaises(AccessError):
            sketch.campaign_id = self.records["campaign_b"]
            sketch.action_save()

    def test_rebuilding_atoms_requires_write_access_to_the_structure(self):
        structure = self.records["structure"]
        self.env["ir.access"].create(
            {
                "name": "Matrix: the structure is locked",
                "model_id": self.env["ir.model"]._get_id("molecular.structure"),
                "group_id": self.env.ref("base.group_everyone").id,
                "kind": "guard",
                "operation": "u",
                "domain": repr([("id", "!=", structure.id)]),
            }
        )
        env = self._principal("user_a")
        for kind in ("atom", "bond"):
            with self.subTest(kind=kind), self.assertRaises(AccessError):
                self.records[kind].with_env(env).unlink()
