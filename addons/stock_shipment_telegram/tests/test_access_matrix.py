from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

OPERATE = (
    "the bot creates and keeps them only through telegram.privilege_operate_bot, "
    "which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestStockShipmentTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "stock_user_a": Persona("stock.group_stock_user"),
        "admin_a": Persona("base.group_system"),
    }
    cells = (
        Cell(
            "telegram.shipment.sheet",
            "sheet_own",
            note="the sender reads the sheets of their own chat; " + OPERATE,
            stock_user_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "telegram.shipment.sheet",
            "sheet_other",
            note="another person's sheets stay theirs; " + OPERATE,
            admin_a="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        credential = env["credential.credential"].create(
            {
                "name": "matrix telegram credential",
                "category_id": env.ref(
                    "credential.credential_category_bearer_token"
                ).id,
                "endpoint_id": env.ref("telegram.service_telegram").id,
            }
        )
        bot = env["telegram.bot"].create(
            {"name": "matrix bot", "credential_id": credential.id}
        )
        warehouse = env["stock.warehouse"].search(
            [("company_id", "=", cls.companies["a"].id)], limit=1
        )
        delivery = env["stock.picking"].create(
            {
                "picking_type_id": warehouse.out_type_id.id,
                "location_id": warehouse.lot_stock_id.id,
                "location_dest_id": env.ref("stock.stock_location_customers").id,
            }
        )

        def sheet(telegram_id, user):
            account = env["telegram.account"]._from_telegram(
                {"id": telegram_id, "first_name": user.name}
            )
            account._bind(user.partner_id, user=user, method="session")
            chat = env["telegram.chat"].create(
                {
                    "chat_id": str(telegram_id),
                    "chat_type": "private",
                    "bot_id": bot.id,
                    "account_id": account.id,
                }
            )
            return env["telegram.shipment.sheet"].create(
                {"bot_id": bot.id, "chat_id": chat.id, "picking_id": delivery.id}
            )

        return {
            "sheet_own": sheet(9601, cls.users["stock_user_a"]),
            "sheet_other": sheet(9602, env.ref("base.user_admin")),
        }
