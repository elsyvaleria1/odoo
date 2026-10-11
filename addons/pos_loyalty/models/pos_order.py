import base64
import logging
from collections import defaultdict

from odoo import Command, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    def check_coupon_programs(self, point_changes, new_codes) -> dict:
        point_changes = {int(k): v for k, v in point_changes.items()}
        coupon_ids_from_pos = set(point_changes.keys())
        coupons = (
            self.env["loyalty.card"]
            .browse(coupon_ids_from_pos)
            .exists()
            .filtered("program_id.active")
        )
        coupon_difference = set(coupons.ids) ^ coupon_ids_from_pos
        if coupon_difference:
            return {
                "successful": False,
                "payload": {
                    "message": self.env._(
                        "Some coupons are invalid. The applied coupons have been updated. Please check the order."
                    ),
                    "removed_coupons": list(coupon_difference),
                },
            }
        for coupon in coupons:
            if float_compare(coupon.points, -point_changes[coupon.id], 2) == -1:
                return {
                    "successful": False,
                    "payload": {
                        "message": self.env._(
                            "There are not enough points for the coupon: %s.",
                            coupon.code,
                        ),
                        "updated_points": {c.id: c.points for c in coupons},
                    },
                }
        coupons = self.env["loyalty.card"].search([("code", "in", new_codes)])
        if coupons:
            return {
                "successful": False,
                "payload": {
                    "message": self.env._(
                        "The following codes already exist in the database, perhaps they were already sold?\n%s",
                        ", ".join(coupons.mapped("code")),
                    ),
                },
            }
        return {
            "successful": True,
            "payload": {},
        }

    def add_loyalty_history_lines(self, coupon_data, coupon_updates) -> None:
        id_mapping = {item["old_id"]: int(item["id"]) for item in coupon_updates}
        history_lines_create_vals = []
        for coupon in coupon_data:
            card_id = id_mapping.get(int(coupon["card_id"]), False) or int(
                coupon["card_id"]
            )
            if not self.env["loyalty.card"].browse(card_id).exists():
                continue
            issued = coupon["won"]
            cost = coupon["spent"]
            if (issued or cost) and card_id > 0:
                history_lines_create_vals.append(
                    {
                        "card_id": card_id,
                        "order_model": self._name,
                        "order_id": self.id,
                        "description": self.env._("Onsite %s", self.display_name),
                        "used": cost,
                        "issued": issued,
                    }
                )
        self.env["loyalty.history"].create(history_lines_create_vals)

    def confirm_coupon_programs(self, coupon_data) -> dict:

        def get_partner_id(partner_id):
            return (
                partner_id
                and self.env["res.partner"].browse(partner_id).exists()
                and partner_id
            ) or False

        coupon_data = {int(k): v for k, v in coupon_data.items()}

        self._check_existing_loyalty_cards(coupon_data)
        self._remove_duplicate_coupon_data(coupon_data)
        self._waive_discounts_without_a_positive_total(coupon_data)
        self._process_existing_gift_cards(coupon_data)

        coupon_new_id_map = {k: k for k in coupon_data if k > 0}

        coupons_to_create = {k: v for k, v in coupon_data.items() if k < 0}
        coupon_create_vals = [
            {
                "program_id": p["program_id"],
                "partner_id": get_partner_id(p.get("partner_id", self.partner_id.id)),
                "code": p.get("code")
                or p.get("barcode")
                or self.env["loyalty.card"]._prepare_code(),
                "points": 0,
                "source_pos_order_id": self.id,
                "expiration_date": p.get("expiration_date"),
            }
            for p in coupons_to_create.values()
        ]

        new_coupons = (
            self.env["loyalty.card"]
            .with_context(action_no_send_mail=True)
            .sudo()
            .create(coupon_create_vals)
        )

        for old_id, new_id in zip(coupons_to_create.keys(), new_coupons, strict=False):
            coupon_new_id_map[new_id.id] = old_id

        all_coupons = (
            self.env["loyalty.card"].sudo().browse(coupon_new_id_map.keys()).exists()
        )
        lines_per_reward_code = defaultdict(lambda: self.env["pos.order.line"])
        for line in self.lines:
            if not line.reward_identifier_code:
                continue
            lines_per_reward_code[line.reward_identifier_code] |= line
        for coupon in all_coupons:
            if coupon.id in coupon_new_id_map:
                coupon.points += coupon_data[coupon_new_id_map[coupon.id]]["points"]
            for reward_code in coupon_data[coupon_new_id_map[coupon.id]].get(
                "line_codes", []
            ):
                lines_per_reward_code[reward_code].coupon_id = coupon
        new_coupons.with_context(
            action_no_send_mail=False
        )._send_creation_communication()
        report_per_program = {}
        coupon_per_report = defaultdict(list)
        for coupon in new_coupons:
            if coupon.program_id not in report_per_program:
                report_per_program[coupon.program_id] = (
                    coupon.program_id.communication_plan_ids.filtered(
                        lambda c: c.trigger == "create"
                    ).pos_report_print_id
                )
            for report in report_per_program[coupon.program_id]:
                coupon_per_report[report.id].append(coupon.id)

        loyalty_points = [
            {
                "order_id": self.id,
                "card_id": coupon_id,
                "spent": -coupon_vals["points"] if coupon_vals["points"] < 0 else 0,
                "won": max(0, coupon_vals["points"]),
            }
            for coupon_id, coupon_vals in coupon_data.items()
        ]
        coupon_updates = [
            {
                "id": coupon.id,
                "old_id": coupon_new_id_map[coupon.id],
            }
            for coupon in all_coupons
        ]
        self.add_loyalty_history_lines(loyalty_points, coupon_updates)

        return {
            "coupon_updates": [
                {
                    "old_id": coupon_new_id_map[coupon.id],
                    "id": coupon.id,
                    "points": coupon.points,
                    "code": coupon.code,
                    "program_id": coupon.program_id.id,
                    "partner_id": coupon.partner_id.id,
                }
                for coupon in all_coupons
                if coupon.program_id.is_nominative
            ],
            "program_updates": [
                {
                    "program_id": program.id,
                    "usages": program.sudo().total_order_count,
                }
                for program in all_coupons.program_id
            ],
            "new_coupon_info": [
                {
                    "program_name": coupon.program_id.name,
                    "expiration_date": coupon.expiration_date,
                    "code": coupon.code,
                }
                for coupon in new_coupons
                if (
                    coupon.program_id.applies_on == "future"
                    and coupon.program_id.sudo().program_type
                    not in ["gift_card", "ewallet"]
                )
            ],
            "coupon_report": coupon_per_report,
        }

    def _process_existing_gift_cards(self, coupon_data):
        updated_gift_cards = self.env["loyalty.card"]
        coupon_key_to_remove = []
        for coupon_id, coupon_vals in coupon_data.items():
            program_id = self.env["loyalty.program"].browse(coupon_vals["program_id"])
            if program_id.program_type == "gift_card":
                updated = False
                gift_card = self.env["loyalty.card"].search(
                    [
                        ("|"),
                        ("code", "=", coupon_vals.get("code", "")),
                        ("id", "=", coupon_vals.get("coupon_id", False)),
                    ]
                )
                if not gift_card.exists():
                    continue

                if not gift_card.partner_id and self.partner_id:
                    updated = True
                    gift_card.partner_id = self.partner_id
                    gift_card.history_ids.create(
                        {
                            "card_id": gift_card.id,
                            "description": self.env._(
                                "Assigning partner %s", self.partner_id.name
                            ),
                            "used": 0,
                            "issued": gift_card.points,
                        }
                    )

                if (
                    len(
                        [
                            id
                            for id in gift_card.history_ids.mapped("order_id")
                            if id != 0
                        ]
                    )
                    == 0
                ):
                    updated = True
                    gift_card.source_pos_order_id = self.id
                    gift_card.history_ids.create(
                        {
                            "card_id": gift_card.id,
                            "order_model": self._name,
                            "order_id": self.id,
                            "description": self.env._(
                                "Assigning order %s", self.display_name
                            ),
                            "used": 0,
                            "issued": gift_card.points,
                        }
                    )

                if coupon_vals.get("points") != gift_card.points:
                    updated = True
                    new_value = gift_card.points + coupon_vals["points"]
                    gift_card.points = new_value
                    gift_card.history_ids.create(
                        {
                            "card_id": gift_card.id,
                            "order_model": self._name,
                            "order_id": self.id,
                            "description": self.env._("Onsite %s", self.display_name),
                            "used": -coupon_vals["points"]
                            if coupon_vals["points"] < 0
                            else 0,
                            "issued": max(0, coupon_vals["points"]),
                        }
                    )

                if updated:
                    updated_gift_cards |= gift_card

                coupon_key_to_remove.append(coupon_id)

        for key in coupon_key_to_remove:
            coupon_data.pop(key, None)

        return updated_gift_cards

    def _get_discount_lines_without_a_positive_total(self):
        self.check_singleton()
        reward_lines = self.lines.filtered("is_reward_line")
        goods_total = sum((self.lines - reward_lines).mapped("price_subtotal_incl"))
        if self.currency_id.compare_amounts(goods_total, 0) > 0:
            return self.env["pos.order.line"]
        return reward_lines.filtered(
            lambda line: line.reward_id.reward_type == "discount"
        )

    def _waive_discounts_without_a_positive_total(self, coupon_data) -> None:
        discount_lines = self._get_discount_lines_without_a_positive_total()
        if not discount_lines:
            return
        waived = 0.0
        for coupon_vals in coupon_data.values():
            line_codes = set(coupon_vals.get("line_codes", ()))
            cost = sum(
                line.points_cost
                for line in discount_lines
                if line.reward_identifier_code in line_codes
            )
            coupon_vals["points"] += cost
            waived += cost
        if waived:
            _logger.warning(
                "PoS order %s carries discount rewards %s without a positive total; "
                "their %s points were not charged",
                self.name,
                discount_lines.reward_id.ids,
                waived,
            )

    def _check_existing_loyalty_cards(self, coupon_data) -> None:
        coupon_key_to_modify = []
        for coupon_id, coupon_vals in coupon_data.items():
            partner_id = coupon_vals.get("partner_id", False)
            if partner_id:
                existing_coupon_for_program = self.env["loyalty.card"].search(
                    [
                        ("partner_id", "=", partner_id),
                        ("program_type", "in", ["loyalty", "ewallet"]),
                        ("program_id", "=", coupon_vals["program_id"]),
                    ]
                )
                if existing_coupon_for_program:
                    coupon_vals["coupon_id"] = existing_coupon_for_program[0].id
                    coupon_key_to_modify.append(
                        [coupon_id, existing_coupon_for_program[0].id]
                    )
        for old_key, new_key in coupon_key_to_modify:
            coupon_data[new_key] = coupon_data.pop(old_key)

    def _remove_duplicate_coupon_data(self, coupon_data) -> None:
        items_to_remove = []
        for coupon_id, coupon_vals in coupon_data.items():
            existing_history = self.env["loyalty.history"].search_count(
                [
                    ("card_id.program_id", "=", coupon_vals["program_id"]),
                    ("order_model", "=", self._name),
                    ("order_id", "=", self.id),
                ]
            )
            if existing_history:
                items_to_remove.append(coupon_id)
        for item in items_to_remove:
            coupon_data.pop(item)

    def _create_mail_attachments(self, name, ticket, basic_ticket):
        attachment = super()._create_mail_attachments(name, ticket, basic_ticket)
        gift_card_programs = self.config_id._get_program_ids().filtered(
            lambda p: p.program_type == "gift_card" and p.pos_report_print_id
        )
        if gift_card_programs:
            gift_cards = self.env["loyalty.card"].search(
                [
                    ("source_pos_order_id", "=", self.id),
                    ("program_id", "in", gift_card_programs.ids),
                ]
            )
            if gift_cards:
                gift_cards_by_program = gift_cards.grouped("program_id")
                for program in gift_card_programs:
                    filtered_gift_cards = gift_cards_by_program.get(program)
                    if filtered_gift_cards:
                        action_report = program.pos_report_print_id
                        report = action_report._render_qweb_pdf(
                            action_report.report_name, filtered_gift_cards.ids
                        )
                        filename = name + ".pdf"
                        gift_card_pdf = self.env["ir.attachment"].create(
                            {
                                "name": filename,
                                "type": "binary",
                                "datas": base64.b64encode(report[0]),
                                "store_fname": filename,
                                "res_model": "pos.order",
                                "res_id": self.ids[0],
                                "mimetype": "application/x-pdf",
                            }
                        )
                        attachment += [Command.link(gift_card_pdf.id)]

        return attachment
