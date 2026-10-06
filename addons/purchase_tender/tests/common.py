from odoo.tests import common


class TestPurchaseTenderCommon(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env.user.group_ids += cls.env.ref("uom.group_uom")

        user_group_purchase_manager = cls.env.ref("purchase.group_purchase_manager")
        user_group_purchase_user = cls.env.ref("purchase.group_purchase_user")

        Users = cls.env["res.users"].with_context({"tracking_disable": True})

        cls.user_purchase_tender_manager = Users.create(
            {
                "name": "Purchase tender Manager",
                "login": "prm",
                "email": "tender_manager@yourcompany.com",
                "notification_type": "inbox",
                "group_ids": [(6, 0, [user_group_purchase_manager.id])],
            }
        )

        cls.user_purchase_tender_user = Users.create(
            {
                "name": "Purchase tender User",
                "login": "pru",
                "email": "tender_user@yourcompany.com",
                "notification_type": "inbox",
                "group_ids": [(6, 0, [user_group_purchase_user.id])],
            }
        )

        cls.product_uom_id = cls.env.ref("uom.product_uom_unit")

        cls.product_09 = cls.env["product.product"].create(
            {
                "name": "Pedal Bin",
                "standard_price": 10.0,
                "list_price": 47.0,
                "type": "consu",
                "uom_id": cls.product_uom_id.id,
                "default_code": "E-COM10",
            }
        )

        cls.product_13 = cls.env["product.product"].create(
            {
                "name": "Corner Desk Black",
                "standard_price": 78.0,
                "list_price": 85.0,
                "type": "consu",
                "uom_id": cls.product_uom_id.id,
                "default_code": "FURN_1118",
            }
        )

        cls.res_partner_1 = cls.env["res.partner"].create(
            {
                "name": "Wood Corner",
            }
        )
