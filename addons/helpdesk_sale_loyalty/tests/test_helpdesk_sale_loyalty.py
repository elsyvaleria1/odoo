from odoo.tests import Form

from odoo.addons.helpdesk.tests import common


class TestHelpdeskSaleCoupon(common.HelpdeskCommon):
    def test_helpdesk_sale_loyalty(self):
        self.test_team.helpdesk_use_coupons = True

        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "test",
                "partner_id": self.partner.id,
                "team_id": self.test_team.id,
            }
        )
        program = self.env["loyalty.program"].create(
            {
                "name": "test program",
                "program_type": "coupons",
                "trigger": "with_code",
                "applies_on": "current",
                "reward_ids": [
                    (
                        0,
                        0,
                        {
                            "reward_type": "discount",
                            "discount": 10,
                            "discount_mode": "percent",
                            "discount_applicability": "order",
                        },
                    )
                ],
            }
        )

        coupon_form = Form(
            self.env["wizard.helpdesk.ticket.create.coupon"].with_context(
                {
                    "active_model": "helpdesk.ticket",
                    "default_ticket_id": ticket.id,
                }
            )
        )
        coupon_form.program = program
        sale_coupon = coupon_form.save()
        sale_coupon.action_coupon_generate_send()

        coupon = self.env["loyalty.card"].search(
            [("partner_id", "=", self.partner.id), ("program_id", "=", program.id)]
        )

        self.assertEqual(len(coupon), 1, "No coupon created")
        self.assertEqual(
            len(ticket.coupon_ids), 1, "The ticket is not linked to a coupon"
        )
        self.assertEqual(
            coupon[0],
            ticket.coupon_ids[0],
            "The correct coupon should be referenced in the ticket",
        )
