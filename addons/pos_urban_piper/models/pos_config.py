import secrets

import psycopg

from odoo import SUPERUSER_ID, Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.modules.registry import Registry
from odoo.tools import SQL

from .account_chart_template import URBANPIPER_FISCAL_POSITION
from .pos_urban_piper_request import UrbanPiperClient
from odoo.addons.pos_urban_piper import const


class PosConfig(models.Model):
    _name = "pos.config"
    _inherit = ["pos.config", "mixin.integration.connected"]

    def _integration_connection_service(self):
        return "urban_piper", self.env._("Point of Sale: Urban Piper"), "other"

    def _default_payment_method_ids(self):
        """
        Override default payment methods to filter out delivery payment methods.
        """
        payment_methods = super()._default_payment_method_ids()
        return payment_methods.filtered(lambda pm: not pm.is_delivery_payment)

    def _default_urbanpiper_store_identifier(self):
        """
        Default unique Urban Piper POS ID.
        """
        return secrets.token_hex()

    def _urbanpiper_pricelist_of(self, company):
        return self.env["product.pricelist"].search(
            [
                ("name", "ilike", "Urbanpiper"),
                ("currency_id", "=", company.currency_id.id),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )

    def _urbanpiper_fiscal_position_of(self, company):
        fiscal_position = self.env.ref(
            self.env["account.chart.template"].company_xmlid(
                URBANPIPER_FISCAL_POSITION, company
            ),
            raise_if_not_found=False,
        )
        if fiscal_position and fiscal_position.sudo().company_id == company:
            return fiscal_position
        return self.env["account.fiscal.position"].search(
            [("name", "=ilike", "urbanpiper"), ("company_id", "=", company.id)],
            limit=1,
        )

    name = fields.Char(translate=True)
    urbanpiper_store_identifier = fields.Char(
        string="Urban Piper POS ID",
        default=lambda self: self._default_urbanpiper_store_identifier(),
        copy=False,
        help="Pos ID from Urban Piper (Atlas)",
    )
    urbanpiper_pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        string="Urban Piper Pricelist",
        compute="_compute_urbanpiper_pricelist_id",
        precompute=True,
        store=True,
        readonly=False,
        help="Pricelist for Urban Piper sync menu.",
    )
    urbanpiper_fiscal_position_id = fields.Many2one(
        comodel_name="account.fiscal.position",
        string="Urban Piper Fiscal Position",
        compute="_compute_urbanpiper_fiscal_position_id",
        precompute=True,
        store=True,
        readonly=False,
        check_company=True,
        help="Fiscal position for Urban Piper sync menu.",
    )
    urbanpiper_payment_methods_ids = fields.Many2many(
        comodel_name="pos.payment.method",
        relation="pos_config_urbanpiper_payment_method_ids_rel",
        column1="config_id",
        string="Urban Piper Payment Methods",
        help="Payment methods for Urban Piper sync menu.",
    )
    urbanpiper_last_sync_date = fields.Datetime(
        string="Last Sync on",
        help="Last sync date for menu sync.",
    )
    urbanpiper_webhook_url = fields.Char(
        string="Register Urbanpiper Webhook URL",
        help="Store webhook url (base url) for security.",
    )
    urbanpiper_delivery_provider_ids = fields.Many2many(
        comodel_name="pos.delivery.provider",
        string="Delivery Providers",
        help="The delivery providers used for online delivery through UrbanPiper.",
    )

    _urbanpiper_store_identifier_uniq = models.Constraint(
        "unique(urbanpiper_store_identifier)",
        "Store ID must be unique for every pos configuration.",
    )

    @api.depends("company_id")
    def _compute_urbanpiper_pricelist_id(self) -> None:
        for config in self:
            if config.urbanpiper_pricelist_id.company_id in (
                config.company_id,
                self.env["res.company"],
            ):
                continue
            config.urbanpiper_pricelist_id = config._urbanpiper_pricelist_of(
                config.company_id
            )

    @api.depends("company_id")
    def _compute_urbanpiper_fiscal_position_id(self) -> None:
        for config in self:
            if config.urbanpiper_fiscal_position_id.company_id == config.company_id:
                continue
            config.urbanpiper_fiscal_position_id = (
                config._urbanpiper_fiscal_position_of(config.company_id)
            )

    def _init_column(self, column_name, *, new_column=False):
        if column_name != "urbanpiper_store_identifier":
            return super()._init_column(column_name, new_column=new_column)
        # fetch void columns
        self.env.cr.execute(
            SQL("SELECT id FROM pos_config WHERE urbanpiper_store_identifier IS NULL")
        )
        pos_config_ids = self.env.cr.fetchall()
        if not pos_config_ids:
            return None
        # update existing columns
        for pos_config_id in pos_config_ids:
            self.env.cr.execute(
                SQL(
                    """
                UPDATE pos_config SET urbanpiper_store_identifier = %s WHERE id = %s;
                """,
                    self._default_urbanpiper_store_identifier(),
                    pos_config_id[0],
                )
            )
        return None

    @api.model_create_multi
    def create(self, vals_list):
        pos_configs = super().create(vals_list)
        for config in pos_configs:
            if config.module_pos_urban_piper:
                config._setup_journals_and_payment_methods()
                config._configure_fiscal_position_and_pricelist()
        return pos_configs

    def write(self, vals):
        res = super().write(vals)
        for config in self:
            if (
                config.module_pos_urban_piper or vals.get("module_pos_urban_piper")
            ) and vals.get("urbanpiper_store_identifier"):
                if not config.urbanpiper_payment_methods_ids or vals.get(
                    "urbanpiper_delivery_provider_ids"
                ):
                    config._setup_journals_and_payment_methods()
                config._configure_fiscal_position_and_pricelist()
        return res

    def _setup_journals_and_payment_methods(self) -> None:
        """
        Fetch or create payment methods and enable option fiscal taxes.
        """
        self.check_singleton()
        delivery_providers = self.urbanpiper_delivery_provider_ids
        for delivery_provider in delivery_providers:
            journal = (
                self.env["account.journal"]
                .sudo()
                .search(
                    [
                        ("code", "=", f"{delivery_provider.journal_code}{self.id}"),
                        ("company_id", "=", self.company_id.id),
                    ],
                    limit=1,
                )
            )
            if not journal:
                journal = (
                    self.env["account.journal"]
                    .sudo()
                    .create(
                        {
                            "name": f"{delivery_provider.name} - {self.name}",
                            "code": f"{delivery_provider.journal_code}{self.id}",
                            "type": "bank",
                            "company_id": self.company_id.id,
                        }
                    )
                )
            payment_method = (
                self.env["pos.payment.method"]
                .sudo()
                .search(
                    [
                        ("journal_id", "=", journal.id),
                        ("is_delivery_payment", "=", True),
                        ("delivery_provider_id", "=", delivery_provider.id),
                    ],
                    limit=1,
                )
            )
            if not payment_method:
                payment_method = (
                    self.env["pos.payment.method"]
                    .sudo()
                    .create(
                        {
                            "name": f"{delivery_provider.name} - {self.name}",
                            "journal_id": journal.id,
                            "company_id": self.company_id.id,
                            "is_delivery_payment": True,
                            "delivery_provider_id": delivery_provider.id,
                        }
                    )
                )
            self.urbanpiper_payment_methods_ids |= payment_method

    def _configure_fiscal_position_and_pricelist(self) -> None:
        """
        Set taxes in fiscal position for urban piper.
        """
        self.check_singleton()
        fiscal_position = (
            self.urbanpiper_fiscal_position_id
            or self._urbanpiper_fiscal_position_of(self.company_id)
            or self.env["account.fiscal.position"].create(
                {"name": "UrbanPiper", "company_id": self.company_id.id}
            )
        )
        if self.module_pos_urban_piper:
            if not self.urbanpiper_fiscal_position_id:
                self.urbanpiper_fiscal_position_id = fiscal_position
            if not self.urbanpiper_pricelist_id:
                pricelist = self._urbanpiper_pricelist_of(self.company_id)
                if not pricelist:
                    pricelist = self.env["product.pricelist"].create(
                        {
                            "name": "UrbanPiper",
                            "company_id": self.company_id.id,
                            "currency_id": self.company_id.currency_id.id,
                            "item_ids": [
                                Command.create(
                                    {
                                        "compute_price": "percentage",
                                        "percent_price": -30,
                                    }
                                )
                            ],
                        }
                    )
                self.urbanpiper_pricelist_id = pricelist.id
        self._add_line_to_fiscal_position(fiscal_position)

    def _add_line_to_fiscal_position(self, fiscal_position):
        # Outside of India, prices are tax-inclusive. So if users want tax-specific behavior,
        # they must manually add a tax line to the fiscal position.
        pass

    def prepare_taxes_data(self, pos_products):
        """
        Prepare taxes data for urban piper for sync menu.
        """
        return []

    def update_urbanpiper_item_data(self, item, product):
        """
        Override this method to update item data with product information. (as per requirements for different regions)
        """
        self.check_singleton()
        return item

    def update_store_status(self, status) -> None:
        """
        Activate and Deactivate store
        """
        user_name = self.env.registry.settings.get(
            self.env, "pos_urban_piper.urbanpiper_username", False
        )
        api_key = self.env.registry.settings.get(
            self.env, "pos_urban_piper.urbanpiper_apikey", False
        )
        if not (user_name == "demo" or api_key == "demo"):
            up = UrbanPiperClient(
                self.with_context(provider_name=self.env.context.get("providerName"))
            )
            up.configure_webhook()
            up.urbanpiper_store_status_update(status=status)

    def order_status_update(
        self, order_id, new_status, code=None, urban_piper_test=False, extra_args=None
    ) -> dict:
        """
        Update order status from urban piper webhook
        """
        if extra_args is None:
            extra_args = {}
        self.check_singleton()
        order = self.env["pos.order"].browse(order_id)
        if new_status == "Food Ready" and order.state != "paid":
            self._create_order_payment(order)
        up = UrbanPiperClient(self)
        is_success, message = False, ""
        order.prep_time = extra_args.get("orderPrepTime", 0)
        if urban_piper_test or (
            order.delivery_provider_id.technical_name == "careem"
            and new_status == "Food Ready"
        ):
            is_success = True
        else:
            is_success, message = up.request_status_update(
                order.delivery_identifier, new_status, order.prep_time, code
            )
        if is_success:
            order.write(
                {
                    "delivery_status": const.ORDER_STATUS_MAPPING[new_status][1],
                }
            )
        if not urban_piper_test and new_status == "Acknowledged":
            up.urbanpiper_order_reference_update(order)
        if new_status == "Cancelled":
            # Prevent loading cancelled orders in `getServerOrders` triggered by `_send_delivery_order_count`
            order.state = "cancel"
        self._send_delivery_order_count(order_id)
        return {"is_success": is_success, "message": message}

    def _create_order_payment(self, order) -> None:
        """
        Make payment for order of urban piper orders.
        """
        self.check_singleton()
        payment_method = self.urbanpiper_payment_methods_ids.filtered(
            lambda pm: pm.delivery_provider_id.id == order.delivery_provider_id.id
        )
        if not payment_method:
            payment_method = self.urbanpiper_payment_methods_ids[0]
        context_payment = {"active_ids": [order.id], "active_id": order.id}
        self.env["wizard.pos.order.pay"].with_context(context_payment).create(
            {
                "amount": order.amount_total,
                "payment_method_id": payment_method.id,
            }
        ).action_make_payment()
        order._recompute_amounts()

    def _send_delivery_order_count(self, order_id=None) -> None:
        """
        Send delivery order count to pos ui
        """
        self.check_singleton()
        if self.current_session_id:
            self._notify("DELIVERY_ORDER_COUNT", order_id)

    def _store_action_update(self, data) -> None:
        """
        Send store status update to pos ui
        """
        self.check_singleton()
        if self.current_session_id:
            self._notify("STORE_ACTION", data)

    def get_delivery_data(self) -> dict:
        """
        Fetch delivery order count and providers for pos ui
        """
        self.check_singleton()
        delivery_order_count = self._get_urbanpiper_order_count()
        delivery_providers = self._get_active_delivery_providers()
        total_new_order = sum(
            provider_data.get("awaiting", 0)
            for provider_data in delivery_order_count["urbanpiper"].values()
        )
        return {
            "delivery_order_count": delivery_order_count,
            "delivery_providers": delivery_providers,
            "total_new_order": total_new_order,
        }

    def _get_total_tax_tag(self):
        self.check_singleton()
        return "total_included"

    def _get_urbanpiper_order_count(self) -> dict:
        """
        Updates order count whenever order status changes and when new order receives
        """
        self.check_singleton()
        if not self.current_session_id:
            return {}
        session_id = self.current_session_id.id
        order_statuses = [
            "placed",
            "acknowledged",
            "food_ready",
            "dispatched",
            "completed",
        ]
        order_count_data = {}
        for provider in self.urbanpiper_delivery_provider_ids:
            order_counts = {
                status: self.env["pos.order"].search_count(
                    [
                        ("delivery_status", "=", status),
                        ("delivery_provider_id", "=", provider.id),
                        ("session_id", "=", session_id),
                        ("state", "!=", "cancel"),
                    ]
                )
                for status in order_statuses
            }
            order_count_data[provider.technical_name] = {
                "awaiting": order_counts["placed"],
                "preparing": order_counts["acknowledged"],
                "done": order_counts["food_ready"]
                + order_counts["dispatched"]
                + order_counts["completed"],
            }
        return {"urbanpiper": order_count_data}

    def _get_active_delivery_providers(self) -> list:
        """
        Fetch delivery providers for pos ui
        """
        return [
            {
                "code": provider.technical_name,
                "name": provider.name,
                "image": provider.image_128,
                "id": provider.id,
            }
            for provider in self.urbanpiper_delivery_provider_ids or []
        ]

    def _urbanpiper_handle_response(
        self, response_json, raise_exception=False
    ) -> dict | None:
        """
        Handle response from urban piper
        """
        title, msg_type, message = self.env._("Urban Piper"), "danger", ""
        if response_json.get("errors"):
            title = next(iter(response_json.get("errors").keys()))
            message = next(iter(response_json.get("errors").values()))
        elif response_json.get("message") or response_json.get("error_message"):
            message = response_json.get("message") or response_json.get("error_message")
        if message:
            if response_json.get("status") == "success":
                msg_type = "success"
                message = message.split(".")[0]
            elif response_json.get("status") == "error":
                if raise_exception:
                    raise ValidationError(message)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": title,
                    "message": message,
                    "type": msg_type,
                    "sticky": False,
                    "next": {
                        "type": "ir.actions.act_window_close"
                    },  # force a form reload
                },
            }
        return None

    def prepare_store_data(self, data):
        self.check_singleton()
        return data

    def _check_required_request_params(self, store_required=True) -> None:
        msg = ""
        if not self.env.company.pos_urbanpiper_username:
            msg += self.env._("UrbanPiper Username is required.\n")
        if not UrbanPiperClient(self)._api_key():
            msg += self.env._("UrbanPiper API Key is required.\n")
        if not self.urbanpiper_store_identifier and store_required:
            msg += self.env._("UrbanPiper Store ID is required.\n")
        if msg:
            raise UserError(msg)

    def log_xml(self, xml_string, func, name="Urbanpiper Logger") -> None:
        self.env.flush_all()
        db_name = self.env.cr.dbname

        try:
            with Registry(db_name).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                IrLogging = env["ir.logging"]
                IrLogging.sudo().create(
                    {
                        "name": name,
                        "type": "server",
                        "dbname": db_name,
                        "level": "DEBUG",
                        "message": xml_string,
                        "path": "Urbanpiper",
                        "func": func,
                        "line": 1,
                    }
                )
        except psycopg.Error:
            pass

    def _reset_urbanpiper_product_linkages(self) -> None:
        """
        Reset product linkage to Urbanpiper and products become available
        for syncing again.
        """
        if linked_statuses := self.env["product.urban.piper.status"].search(
            [("config_id", "in", self.ids), ("is_product_linked", "=", True)]
        ):
            linked_statuses.write({"is_product_linked": False})

    def _get_urban_piper_toggle_states(self):
        # get_param's default applies only when the key is ABSENT. The post-init
        # hook plants this one as an empty string, so a two-argument get_param
        # reads "" and json.loads raises -- which is why both callers must go
        # through one reader rather than each deciding what empty means.
        raw = self.env.registry.settings.get(
            self.env, "pos_urban_piper.toggle_state", False
        )
        return json_loads(raw or "{}")

    def get_urban_piper_provider_states(self):
        return self._get_urban_piper_toggle_states().get(str(self.id), {})

    def set_urban_piper_provider_states(self, value_json):
        config_state = self._get_urban_piper_toggle_states()
        config_state[str(self.id)] = json_loads(value_json or "{}")
        self.env["ir.config_parameter"].sudo().set_param(
            "pos_urban_piper.toggle_state", json_dumps(config_state)
        )
        self._notify("URBAN_PIPER_PROVIDER_STATES", config_state[str(self.id)])
        return config_state[str(self.id)]

    def get_urbanpiper_special_products(self) -> list:
        return [
            self.env.ref(
                "pos_urban_piper.product_other_charges", raise_if_not_found=False
            ),
            self.env.ref(
                "pos_urban_piper.product_delivery_charges", raise_if_not_found=False
            ),
            self.env.ref(
                "pos_urban_piper.product_packaging_charges", raise_if_not_found=False
            ),
        ]
