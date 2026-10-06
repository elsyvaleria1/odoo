from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCheckTeamOnCreate(TransactionCase):
    def test_a_check_takes_the_team_of_its_quality_point(self):
        team = self.env["team.team"].create(
            {"use_quality": True, "name": "Night shift"}
        )
        product = self.env["product.product"].create({"name": "Valve"})
        point = self.env["quality.point"].create(
            {
                "product_ids": [(4, product.id)],
                "test_type_id": self.env.ref("quality.test_type_instructions").id,
                "team_id": team.id,
            }
        )

        check = self.env["quality.check"].create(
            {"product_id": product.id, "point_id": point.id}
        )

        self.assertEqual(check.team_id, team)
