from collections import Counter
from typing import Self

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockQuant(models.Model):
    _inherit = "stock.quant"

    dummy_id = fields.Char(
        compute="_compute_dummy_id",
        inverse="_inverse_dummy_id",
    )
    image_1920 = fields.Image(related="product_id.image_1920")
    product_reference_code = fields.Char(
        related="product_id.code",
        string="Product Reference Code",
    )

    def _compute_dummy_id(self) -> None:
        self.dummy_id = ""

    def _inverse_dummy_id(self):
        pass

    @api.model
    def barcode_write(self, vals):
        """Specially made to handle barcode app saving. Avoids overriding write method because pickings in barcode
        will also write to quants and handling context in this case is non-trivial. This method is expected to be
        called only when no record and vals is a list of lists of the form: [[1, quant_id, {write_values}],
        [0, 0, {write_values}], ...]} where [1, quant_id...] updates an existing quant or {[0, 0, ...]}
        when creating a new quant."""
        _debug.lifecycle("quant_barcode_write", quants=self, fields=len(vals))
        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        self._barcode_resolve_lot_names(vals, Quant)

        quant_ids = []
        for command, quant_id, quant_vals in vals:
            if command == 1:
                Quant.browse(quant_id).write(quant_vals)
                quant_ids.append(quant_id)
            elif command == 0:
                quant = Quant.create(quant_vals)
                # `Quant.create` may return an EXISTING quant rather than a new one (it happens
                # when scanning a product whose quants don't show up in the view because they are
                # assigned to nobody or carry no inventory date), and on that path
                # `stock.quant._prepare_inventory_move_vals`' caller overwrites `inventory_date`
                # with today — see `addons/stock/models/stock_quant.py`, the `quant.user_id = …`
                # / `quant.inventory_date = fields.Date.today()` pair. The date the barcode app
                # counted against therefore has to be restored.
                if quant_vals.get("inventory_date"):
                    # Only when given: the previous unconditional write cleared the date to False
                    # whenever the key was absent.
                    quant.write({"inventory_date": quant_vals["inventory_date"]})
                # `user_id` needs nothing here: the same core branch already assigns it, falling
                # back to the current user. (It assigns it even when the quant belonged to
                # somebody else, which reassigns their count — real, but core's to fix, not this
                # module's to work around.)
                quant_ids.append(quant.id)
        return self.browse(quant_ids)._get_stock_barcode_data()

    @api.model
    def _barcode_resolve_lot_names(self, vals, Quant) -> None:
        """Turn each command's ``lot_name`` into a ``trace_id``, reusing the lot when one already
        exists for that (product, name).

        Creating unconditionally raises `product.trace`'s uniqueness constraint — and since the whole
        payload is one transaction, that rejects **every** line the operator counted, not just the
        offending one. Two lines of the same lot in different locations (scan LOT-1 in shelf A,
        walk to shelf B, scan LOT-1 again) is enough to trigger it, so this is a normal counting
        flow rather than an edge case.
        """
        _debug.logic("quant_lot_names_resolve", quants=self)
        Lot = self.env["product.trace"]
        pending = {}  # (product_id, lot_name) -> list of vals dicts waiting for that lot
        for command, quant_id, quant_vals in vals:
            if (
                command not in (0, 1)
                or quant_vals.get("trace_id")
                or not quant_vals.get("lot_name")
            ):
                continue
            product_id = quant_vals.get("product_id")
            if not product_id and command == 1:
                product_id = Quant.browse(quant_id).product_id.id
            pending.setdefault((product_id, quant_vals.pop("lot_name")), []).append(
                quant_vals
            )
        if not pending:
            return

        existing = {
            (lot.product_id.id, lot.name): lot.id
            for lot in Lot.search(
                Domain.OR(
                    Domain("product_id", "=", product_id)
                    & Domain("name", "=", lot_name)
                    for product_id, lot_name in pending
                )
            )
        }
        to_create = [
            {"name": lot_name, "product_id": product_id}
            for product_id, lot_name in pending
            if (product_id, lot_name) not in existing
        ]
        for lot in Lot.create(to_create):
            existing[(lot.product_id.id, lot.name)] = lot.id
        for key, vals_list in pending.items():
            for quant_vals in vals_list:
                quant_vals["trace_id"] = existing[key]

    def action_barcode_remove_count(self) -> None:
        """The inventory line's trash button: forget the operator's count, and the quant
        with it when it only existed to be counted. It used to call `action_validate`,
        which applied the count: a quant of 5 counted to 0 and "deleted" lost its 5 units."""
        _debug.pipeline("quant_barcode_remove_count", quants=self)
        quants = self.with_context(inventory_mode=True)
        quants.action_clear_inventory_quantity()
        quants._remove_zero_quants()

    def action_validate(self):
        _debug.pipeline("quant_barcode_validate", quants=self)
        quants = self.with_context(inventory_mode=True).filtered(
            lambda q: q.inventory_quantity_set
        )
        # The diff does not depend on `quantity`: a quant moved since it was counted would
        # be applied with the difference computed at counting time.
        quants._compute_inventory_diff_quantity()
        return quants.action_apply_inventory() or True

    def _get_stock_barcode_data(self):
        _debug.perf.count("quant_barcode_data", quants=self)
        locations = self.env["stock.location"]
        company_id = self.env.company.id
        package_types = self.env["stock.package.type"]
        valid_quants = self
        if (
            not self
        ):  # `self` is an empty recordset when we open the inventory adjustment.
            warehouse_location = (
                self.env["stock.warehouse"]
                .search([("company_id", "=", company_id)], limit=1)
                .lot_stock_id
            )
            if self.env.user.has_group("stock.group_stock_multi_locations"):
                quant_locations = self.env["stock.location"].search(
                    [
                        ("usage", "in", ["internal", "transit"]),
                        ("company_id", "=", company_id),
                    ],
                    order="id",
                )
            else:
                quant_locations = warehouse_location
            valid_quants = self.env["stock.quant"].search(
                [
                    "|",
                    ("user_id", "=", self.env.user.id),
                    ("user_id", "=", False),
                    ("location_id", "in", quant_locations.ids),
                    ("inventory_date", "<=", fields.Date.context_today(self.env.user)),
                ]
            )
            locations = (
                warehouse_location.child_internal_location_ids
                | valid_quants.location_id
            )
            if self.env.user.has_group("stock.group_tracking_lot"):
                package_types = package_types.search([])

        data = valid_quants.with_context(
            display_default_code=False, barcode_view=True
        ).get_stock_barcode_data_records()
        if locations:
            data["records"]["stock.location"] = locations.read(
                locations._get_fields_stock_barcode(), load=False
            )
        if package_types:
            data["records"]["stock.package.type"] = package_types.read(
                package_types._get_fields_stock_barcode(), load=False
            )
        data["products_with_all_quants"] = valid_quants._get_products_with_all_quants()
        data["line_view_id"] = self.env.ref("stock_barcode.stock_quant_barcode").id
        return data

    def _get_products_with_all_quants(self):
        """The products of `self` whose every internal quant `self` already holds: stated so
        the client does not fetch again what it was sent, without sending more."""
        sent = Counter(
            quant.product_id.id
            for quant in self
            if quant.location_id.usage == "internal"
        )
        if not sent:
            return []
        groups = self._read_group(
            [
                ("product_id", "in", list(sent)),
                ("location_id.usage", "=", "internal"),
            ],
            ["product_id"],
            ["__count"],
        )
        return sorted(
            product.id for product, count in groups if sent[product.id] == count
        )

    @api.model
    def _get_barcode_counting_quants(self, products) -> Self:
        """Every internal quant of `products`: what counting one of them may need."""
        return self.search(
            [
                ("product_id", "in", products.ids),
                ("location_id.usage", "=", "internal"),
            ]
        )

    def get_stock_barcode_counting_data(self):
        """The data to count `self` (a package's content, a location's quants): `quant_ids`
        are the quants to count, `records` also carries every internal quant of their products,
        which `products_with_all_quants` states, so the client fetches none of them again."""
        quants = self | self._get_barcode_counting_quants(self.product_id)
        data = quants.get_stock_barcode_data_records()
        data["quant_ids"] = self.ids
        data["products_with_all_quants"] = self.product_id.ids
        return data

    def get_stock_barcode_data_records(self) -> dict:
        _debug.perf.count("quant_barcode_data_records", quants=self)
        products = self.product_id
        companies = self.company_id or self.env.company
        lots = self.trace_id
        owners = self.owner_id
        # Every ancestor, as the picking payload sends: nested packages go deeper than one.
        packages = self.env["stock.package"].search(
            [("id", "parent_of", self.package_id.ids)]
        )
        # If UoM setting is active, fetch all UoM's data: any of them can be scanned.
        if self.env.user.has_group("base.group_uom"):
            uoms = self.env["uom.uom"].search([])
        else:
            uoms = products.uom_id | products.uom_ids

        return {
            "records": {
                "stock.quant": self.read(self._get_fields_stock_barcode(), load=False),
                "product.product": products.read(
                    products._get_fields_stock_barcode(), load=False
                ),
                "stock.package": packages.read(
                    packages._get_fields_stock_barcode(), load=False
                ),
                "res.company": companies.read(["name"]),
                "res.partner": owners.read(
                    owners._get_fields_stock_barcode(), load=False
                ),
                "product.trace": lots.read(
                    lots._get_fields_stock_barcode(), load=False
                ),
                "uom.uom": uoms.read(uoms._get_fields_stock_barcode(), load=False),
            },
            "nomenclature_id": self.env.company.sudo().barcodes_config_id.nomenclature_id.id,
            "show_quantity_count": self.env.registry.settings.get_bool(
                self.env, "stock.show_expected_quantity_count"
            ),
            "user_id": self.env.user.id,
        }

    def _get_fields_stock_barcode(self):
        return [
            "product_id",
            "location_id",
            "inventory_date",
            "inventory_quantity",
            "inventory_quantity_set",
            "quantity",
            "product_uom_id",
            "trace_id",
            "package_id",
            "owner_id",
            "inventory_diff_quantity",
            "dummy_id",
            "user_id",
        ]

    def _get_inventory_fields_countable(self):
        # Renamed with the base method, which `write()` never consulted: this only
        # ever widened the inventory-mode `create` allowlist.
        return ["dummy_id"] + super()._get_inventory_fields_countable()

    def _get_stock_barcode_specific_data(self) -> dict:
        return {
            "product.product": self.product_id.read(
                self.env["product.product"]._get_fields_stock_barcode(), load=False
            ),
            "uom.uom": self.product_id.uom_id.read(
                self.env["uom.uom"]._get_fields_stock_barcode(), load=False
            ),
            "stock.location": self.location_id.read(
                self.env["stock.location"]._get_fields_stock_barcode(), load=False
            ),
            "product.trace": self.trace_id.read(
                self.env["product.trace"]._get_fields_stock_barcode(), load=False
            ),
            "stock.package": self.package_id.read(
                self.env["stock.package"]._get_fields_stock_barcode(), load=False
            ),
            "res.partner": self.owner_id.read(
                self.env["res.partner"]._get_fields_stock_barcode(), load=False
            ),
        }
