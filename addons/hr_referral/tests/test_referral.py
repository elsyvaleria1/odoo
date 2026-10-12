from odoo.exceptions import UserError
from odoo.libs.json import loads as json_loads

from odoo.addons.hr_referral.tests.common import TestHrReferralBase


class TestHrReferral(TestHrReferralBase):
    def test_referral_share_is_new(self):
        self.job_dev = self.job_dev.with_user(self.richard_user.id)

        self.assertTrue(
            self.env["wizard.hr.job.share.referral.link"]
            .with_user(self.richard_user.id)
            .create({"job_id": self.job_dev.id})
            .url,
            "Reading the computed url is what creates the link tracker",
        )
        links = self.env["link.tracker"].search(
            [("campaign_id", "=", self.job_dev.utm_campaign_id.id)]
        )
        self.assertEqual(len(links), 1, "It should have created only one link tracker")

        self.assertTrue(
            self.env["wizard.hr.job.share.referral.link"]
            .with_user(self.steve_user.id)
            .create({"job_id": self.job_dev.id})
            .url,
            "Reading the computed url is what creates the link tracker",
        )
        links = self.env["link.tracker"].search(
            [("campaign_id", "=", self.job_dev.utm_campaign_id.id)]
        )
        self.assertEqual(
            len(links),
            2,
            "It should have created 2 different links tracker (one for each user)",
        )

    def test_referral_change_referrer(self):
        job_applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Technical worker",
                "job_id": self.job_dev.id,
                "ref_user_id": self.richard_user.id,
                "company_id": self.company_1.id,
            }
        )
        self.assertEqual(
            job_applicant.ref_user_id,
            self.richard_user,
            "Referral is created with the right user",
        )
        points_richard = self.env["hr.referral.points"].search(
            [("ref_user_id", "=", self.richard_user.id)]
        )
        self.assertEqual(
            job_applicant.stage_id.points,
            sum(points_richard.mapped("points")),
            "Right amount of referral points are created.",
        )
        job_applicant.ref_user_id = self.steve_user.id
        self.assertEqual(
            job_applicant.ref_user_id,
            self.steve_user,
            "Referral is modified with as user Steve",
        )
        points_richard = self.env["hr.referral.points"].search(
            [("ref_user_id", "=", self.richard_user.id)]
        )
        self.assertEqual(
            sum(points_richard.mapped("points")), 0, "Richard has no more points"
        )
        points_steve = self.env["hr.referral.points"].search(
            [("ref_user_id", "=", self.steve_user.id)]
        )
        self.assertEqual(
            sum(points_steve.mapped("points")),
            job_applicant.stage_id.points,
            "Right amount of referral points are created for Steve",
        )

    def test_referral_add_points(self):
        with self.assertRaises(UserError):
            self.mug_shop.sudo().buy()
        job_applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Technical worker",
                "job_id": self.job_dev.id,
                "ref_user_id": self.richard_user.id,
                "company_id": self.company_1.id,
            }
        )
        self.assertEqual(
            job_applicant.earned_points,
            job_applicant.stage_id.points,
            "Richard received points corresponding to the first stage.",
        )
        stages = self.env["hr.recruitment.stage"].search([("job_ids", "=", False)])
        job_applicant.stage_id = stages[-2]
        self.assertEqual(
            job_applicant.earned_points,
            sum(stages[:-1].mapped("points")),
            "Richard received points corresponding to the before last stage.",
        )
        self.assertEqual(
            job_applicant.referral_state, "progress", "Referral stay in progress"
        )
        job_applicant.stage_id = stages[-1]
        self.assertEqual(
            job_applicant.earned_points,
            sum(stages.mapped("points")),
            "Richard received points corresponding to the last stage.",
        )
        self.assertEqual(job_applicant.referral_state, "hired", "Referral is hired")
        self.mug_shop.sudo().buy()
        shopped_item = self.env["hr.referral.points"].search(
            [
                ("ref_user_id", "=", self.richard_user.id),
                ("hr_referral_reward_id", "!=", False),
            ]
        )
        self.assertEqual(
            shopped_item.points,
            -self.mug_shop.cost,
            "The item bought decrease the number of points.",
        )

    def test_referral_multi_company(self):
        self.job_dev = self.job_dev.with_user(self.richard_user.id)
        self.assertTrue(
            self.env["wizard.hr.job.share.referral.link"]
            .with_user(self.richard_user.id)
            .create({"job_id": self.job_dev.id})
            .url,
            "Reading the computed url is what creates the link tracker",
        )

        job_applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Technical worker",
                "company_id": self.company_1.id,
                "job_id": self.job_dev.id,
                "source_id": self.richard_user.utm_source_id.id,
                "ref_user_id": self.richard_user.id,
            }
        )
        points_richard_c1 = self.env["hr.referral.points"].search(
            [
                ("ref_user_id", "=", self.richard_user.id),
                ("company_id", "=", self.company_1.id),
            ]
        )
        points_richard_c2 = self.env["hr.referral.points"].search(
            [
                ("ref_user_id", "=", self.richard_user.id),
                ("company_id", "=", self.company_2.id),
            ]
        )
        self.assertEqual(
            job_applicant.stage_id.points,
            sum(points_richard_c1.mapped("points")),
            "Right amount of referral points are created.",
        )
        self.assertEqual(
            0,
            sum(points_richard_c2.mapped("points")),
            "Right amount of referral points are created.",
        )

        self.assertEqual(
            self.red_mug_shop.points_missing,
            self.red_mug_shop.cost,
            "10 points are missing",
        )

    def test_referral_no_hired_stage(self):
        self.env.ref("hr_recruitment.stage_job0").use_in_referral = False
        self.env.ref("hr_recruitment.stage_job3").use_in_referral = False
        stage_parking_1 = self.env["hr.recruitment.stage"].create(
            {
                "name": "parking1",
                "use_in_referral": False,
                "job_ids": [(6, 0, self.job_dev.ids)],
                "sequence": 15,
                "points": 500,
            }
        )
        stage_parking_2 = self.env["hr.recruitment.stage"].create(
            {
                "name": "parking2",
                "use_in_referral": False,
                "job_ids": [(6, 0, self.job_dev.ids)],
                "sequence": 16,
                "points": 1000,
            }
        )
        job_applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Technical worker",
                "job_id": self.job_dev.id,
                "ref_user_id": self.richard_user.id,
                "company_id": self.company_1.id,
                "stage_id": self.env.ref("hr_recruitment.stage_job1").id,
            }
        )

        self.assertEqual(
            self.job_dev.max_points,
            85,
            "Max points for this job is 85 (points for the 3 'not hired stage' are ignored).",
        )
        self.assertEqual(
            job_applicant.earned_points,
            self.env.ref("hr_recruitment.stage_job1").points,
            "Richard received points corresponding to the first stage.",
        )
        self.assertEqual(
            len(job_applicant.referral_points_ids),
            1,
            "Richard received points corresponding to the first stage.",
        )
        info_dashboard = json_loads(job_applicant.shared_item_infos)
        self.assertEqual(
            len(info_dashboard), 4, "In dashboard, we have only not 'not hired stage'."
        )
        self.assertEqual(
            [x["done"] for x in info_dashboard],
            [True, False, False, False],
            "In dashboard, we have only not 'not hired stage' and state are correct.",
        )

        job_applicant.stage_id = self.env.ref("hr_recruitment.stage_job3")
        total_points = (
            self.env.ref("hr_recruitment.stage_job1").points
            + self.env.ref("hr_recruitment.stage_job2").points
        )
        self.assertEqual(
            job_applicant.earned_points,
            total_points,
            "As he jump to a 'not hired stage', he receive points for other stages and the jumped stages are ignored.",
        )
        self.assertEqual(
            len(job_applicant.referral_points_ids),
            2,
            "Richard received points corresponding to the first and second stage.",
        )
        info_dashboard = json_loads(job_applicant.shared_item_infos)
        self.assertEqual(
            [x["done"] for x in info_dashboard],
            [True, True, False, False],
            "In dashboard, we have only not 'not hired stage' and state are correct.",
        )

        job_applicant.stage_id = self.env.ref("hr_recruitment.stage_job1")
        self.assertEqual(
            job_applicant.earned_points,
            self.env.ref("hr_recruitment.stage_job1").points,
            "As he jump from a 'not hired stage' to the stage where he was before the 'not hired stage', he receive no points.",
        )
        self.assertEqual(
            len(job_applicant.referral_points_ids),
            3,
            "Richard received points corresponding to the first and second stages, including the second stage again when we moved the applicant back.",
        )
        info_dashboard = json_loads(job_applicant.shared_item_infos)
        self.assertEqual(
            [x["done"] for x in info_dashboard],
            [True, False, False, False],
            "In dashboard, we have only not 'not hired stage' and state are correct.",
        )

        job_applicant.stage_id = self.env.ref("hr_recruitment.stage_job3")
        total_points = (
            self.env.ref("hr_recruitment.stage_job1").points
            + self.env.ref("hr_recruitment.stage_job2").points
        )
        self.assertEqual(
            job_applicant.earned_points,
            total_points,
            "As he jump to a 'not hired stage', he receive points for other stages and the jumped stages are ignored.",
        )
        self.assertEqual(
            len(job_applicant.referral_points_ids),
            4,
            "Richard received points corresponding to the second stage again.",
        )

        job_applicant.stage_id = self.env.ref("hr_recruitment.stage_job4")
        self.assertEqual(
            job_applicant.earned_points,
            35,
            "He received points for stage 2 and stage 4 (in addition to stage 1 that he already received).",
        )
        self.assertEqual(
            len(job_applicant.referral_points_ids),
            5,
            "3 lines in received points (3 new [2 for stage 2 and 1 for stage 4], 1 old [for stage 1] and 1 for remove [for stage 2]).",
        )
        info_dashboard = json_loads(job_applicant.shared_item_infos)
        self.assertEqual(
            [x["done"] for x in info_dashboard],
            [True, True, True, False],
            "In dashboard, we have only not 'not hired stage' and state are correct.",
        )

        job_applicant.stage_id = stage_parking_1
        job_applicant.stage_id = stage_parking_2
        job_applicant.stage_id = stage_parking_1
        job_applicant.stage_id = self.env.ref("hr_recruitment.stage_job3")
        job_applicant.stage_id = self.env.ref("hr_recruitment.stage_job4")
        self.assertEqual(
            job_applicant.earned_points,
            35,
            "Nothing change as it was only 'not hired stage'.",
        )
        self.assertEqual(
            len(job_applicant.referral_points_ids),
            9,
            "Total line added in received points.",
        )

        job_applicant.stage_id = self.env.ref("hr_recruitment.stage_job5")
        self.assertEqual(job_applicant.earned_points, 85, "He received all points.")
        self.assertEqual(
            len(job_applicant.referral_points_ids),
            10,
            "We add a line in received points.",
        )
        self.assertEqual(
            job_applicant.referral_state,
            "hired",
            "Referral is hired, even if stage (not hired) exist with bigger sequence.",
        )

    def test_referral_no_point_done_stage(self):
        final_stage = self.env.ref("hr_recruitment.stage_job5")
        final_stage.sequence = 20
        stage_parking_1 = self.env["hr.recruitment.stage"].create(
            {
                "name": "parking1",
                "use_in_referral": True,
                "job_ids": [(6, 0, self.job_dev.ids)],
                "sequence": 15,
                "points": 0,
            }
        )
        stage_parking_2 = self.env["hr.recruitment.stage"].create(
            {
                "name": "parking2",
                "use_in_referral": True,
                "job_ids": [(6, 0, self.job_dev.ids)],
                "sequence": 16,
                "points": 0,
            }
        )
        job_applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Technical worker",
                "job_id": self.job_dev.id,
                "ref_user_id": self.richard_user.id,
                "company_id": self.company_1.id,
                "stage_id": self.env.ref("hr_recruitment.stage_job1").id,
            }
        )

        info_dashboard = json_loads(job_applicant.shared_item_infos)
        self.assertEqual(
            [x["done"] for x in info_dashboard],
            [True, True, False, False, False, False, False, False],
        )
        job_applicant.stage_id = stage_parking_2
        info_dashboard = json_loads(job_applicant.shared_item_infos)
        self.assertEqual(
            [x["done"] for x in info_dashboard],
            [True, True, True, True, True, True, True, False],
            "parking1 and parking2 should be marked as done",
        )
        job_applicant.stage_id = stage_parking_1
        info_dashboard = json_loads(job_applicant.shared_item_infos)
        self.assertEqual(
            [x["done"] for x in info_dashboard],
            [True, True, True, True, True, True, False, False],
            "parking2 should not be marked as done anymore",
        )

    def test_referral_reset_applicant(self):
        applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Test Applicant",
                "job_id": self.job_dev.id,
                "ref_user_id": self.richard_user.id,
                "company_id": self.company_1.id,
                "referral_state": "progress",
            }
        )
        applicant.write({"referral_state": "hired"})
        self.assertEqual(
            applicant.referral_state,
            "hired",
            "Applicant referral state should be 'hired'",
        )
        applicant.reset_applicant()
        self.assertEqual(
            applicant.referral_state,
            "progress",
            "After reset_applicant, referral state should be 'progress'",
        )
        applicant.write({"referral_state": "closed"})
        self.assertEqual(
            applicant.referral_state,
            "closed",
            "Applicant referral state should be 'closed'",
        )
        applicant.reset_applicant()
        self.assertEqual(
            applicant.referral_state,
            "progress",
            "After reset_applicant, referral state should be 'progress'",
        )

    def test_referral_reset_applicant_batch(self):
        applicants = self.env["hr.applicant"].create(
            [
                {
                    "partner_name": "Applicant 1",
                    "job_id": self.job_dev.id,
                    "ref_user_id": self.richard_user.id,
                    "company_id": self.company_1.id,
                    "referral_state": "hired",
                },
                {
                    "partner_name": "Applicant 2",
                    "job_id": self.job_dev.id,
                    "ref_user_id": self.steve_user.id,
                    "company_id": self.company_1.id,
                    "referral_state": "closed",
                },
                {
                    "partner_name": "Applicant 3",
                    "job_id": self.job_dev.id,
                    "ref_user_id": self.richard_user.id,
                    "company_id": self.company_1.id,
                    "referral_state": "progress",
                },
            ]
        )
        self.assertEqual(applicants[0].referral_state, "hired")
        self.assertEqual(applicants[1].referral_state, "closed")
        self.assertEqual(applicants[2].referral_state, "progress")
        applicants.reset_applicant()
        for applicant in applicants:
            self.assertEqual(
                applicant.referral_state,
                "progress",
                f"Applicant {applicant.partner_name} should have referral_state 'progress' after reset",
            )

    def test_welcome_screen_acquires_level_after_onboarding(self):
        user = self.richard_user
        user.write(
            {"hr_referral_level_id": False, "hr_referral_onboarding_page": False}
        )
        applicants = self.env["hr.applicant"].with_user(user)
        screen = applicants.acquire_referral_welcome_screen()
        self.assertTrue(screen["onboarding_screen"])
        self.assertFalse(user.hr_referral_level_id)

        user.hr_referral_onboarding_page = True
        first_level = self.env["hr.referral.level"].search(
            [], order="points asc", limit=1
        )
        self.assertTrue(first_level)
        screen = applicants.acquire_referral_welcome_screen()
        self.assertEqual(user.hr_referral_level_id, first_level)
        self.assertEqual(screen["level"]["name"], first_level.name)
        self.assertEqual(screen["id"], user.id)
        self.assertEqual(
            applicants.acquire_referral_welcome_screen()["level"], screen["level"]
        )
        self.assertEqual(user.hr_referral_level_id, first_level)
