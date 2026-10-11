from typing import Self

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import SQL


class MixinResourceScheduling(models.AbstractModel):
    _name = "mixin.resource.scheduling"
    _description = "Resource Scheduling Mixin"
    _inherit = ["mixin.resource.scheduling.tools"]

    _reservation_sync_manual = False

    reservation_ids = fields.One2many(
        comodel_name="resource.reservation",
        inverse_name="res_id",
        string="Reservations",
        copy=False,
        domain=lambda self: [("res_model", "=", self._name)],
        bypass_search_access=True,
    )
    schedule_overlap_count = fields.Integer(
        string="Scheduling Conflicts",
        compute="_compute_schedule_overlap_count",
        search="_search_schedule_overlap_count",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self._reservation_sync_manual:
            records._active_for_sync()._sync_reservations()
        return records

    def write(self, vals):
        result = super().write(vals)
        start_field, end_field = self._get_fields_reservation_date()
        has_dates = bool(start_field and end_field)
        reactivating = bool(vals.get("active")) and has_dates

        if "active" in vals and has_dates and not reactivating:
            mirror_active = bool(vals["active"])
            self.env["resource.reservation"].sudo().with_context(
                active_test=False
            ).search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "in", self.ids),
                    ("active", "!=", mirror_active),
                ]
            ).write({"active": mirror_active})

        triggers = self._get_fields_sync_trigger()
        sync_needed = bool(triggers and triggers.intersection(vals.keys()))
        if (sync_needed or reactivating) and not self._reservation_sync_manual:
            self._active_for_sync()._sync_reservations()
        return result

    def unlink(self):
        model_name, record_ids = self._name, self.ids
        result = super().unlink()
        self.env["resource.reservation"].sudo().with_context(active_test=False).search(
            [
                ("res_model", "=", model_name),
                ("res_id", "in", record_ids),
            ]
        ).unlink()
        return result

    @api.depends(lambda self: self._get_fields_overlap_depends())
    def _compute_schedule_overlap_count(self) -> None:
        conflicts = self._get_schedule_conflicts_batch()
        for record in self:
            record.schedule_overlap_count = len(conflicts[record.id])

    @api.model
    def _search_schedule_overlap_count(self, operator, value):
        if not isinstance(value, int) or value != 0 or operator not in ("=", "!="):
            return NotImplemented
        Reservation = self.env["resource.reservation"].sudo()
        Reservation.flush_model(
            [*Reservation._OVERLAP_SWEEP_FIELDS, "res_model", "res_id"]
        )

        def to_sql(model, alias, query):
            return SQL(
                """%s %s (
                    SELECT this.res_id
                      FROM (%s) AS partners(id, peers)
                      JOIN %s AS this ON this.id = partners.id
                     CROSS JOIN LATERAL unnest(partners.peers) AS peer(id)
                      JOIN %s AS other ON other.id = peer.id
                     WHERE this.res_model = %s
                       AND (other.res_model IS DISTINCT FROM this.res_model
                            OR other.res_id IS DISTINCT FROM this.res_id)
                )""",
                model._field_to_sql(alias, "id", query),
                SQL("NOT IN") if operator == "=" else SQL("IN"),
                Reservation._get_sql_overlap_partners(),
                SQL.identifier(Reservation._table),
                SQL.identifier(Reservation._table),
                model._name,
            )

        return Domain.custom(to_sql=to_sql)

    def _get_fields_reservation_date(self) -> tuple:
        return (None, None)

    def _recompute_first_served_hours(self) -> None:
        pass

    def _get_fields_sync_trigger(self):
        triggers = set()
        start_field, end_field = self._get_fields_reservation_date()
        if start_field:
            triggers.add(start_field)
        if end_field:
            triggers.add(end_field)
        return triggers

    def _get_fields_overlap_depends(self) -> list:
        return [
            "reservation_ids.schedule_overlap_count",
            "reservation_ids.active",
            *sorted(self._get_fields_sync_trigger()),
        ]

    def _get_schedule_conflicts_batch(self):
        reservation_model = self.env["resource.reservation"].sudo()
        empty = reservation_model.browse()
        result = dict.fromkeys(self._ids, empty)

        stored = self.filtered(lambda record: isinstance(record.id, int))
        own_by_record = {record.id: record.reservation_ids.sudo() for record in stored}
        all_own = empty
        for own in own_by_record.values():
            all_own |= own
        if all_own:
            partners = all_own._get_conflicting_reservations()
            for record_id, own in own_by_record.items():
                found = empty
                for reservation in own:
                    found |= partners.get(reservation.id, empty)
                result[record_id] = found - own

        for record in self - stored:
            result[record.id] = reservation_model._get_prospective_conflicts(
                record._prepare_reservation_vals_list(),
                ignore_ids=record._origin.reservation_ids.ids,
            )
        return result

    def _prepare_reservation_vals_list(self):
        self.check_singleton()
        return []

    def _prepare_reservation_vals_by_record(self) -> dict:
        return {record.id: record._prepare_reservation_vals_list() for record in self}

    def _sync_reservations(self) -> None:
        start_field, end_field = self._get_fields_reservation_date()
        if not start_field or not end_field or not self:
            return
        reservation_model = self.env["resource.reservation"]
        existing_all = (
            reservation_model.sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "in", self.ids),
                ]
            )
        )
        existing_by_record = existing_all.grouped("res_id")
        no_reservations = existing_all.browse()
        vals_by_record = self._prepare_reservation_vals_by_record()
        reservation_model._sync_projection_batch(
            (
                record,
                vals_by_record[record.id],
                existing_by_record.get(record.id, no_reservations),
            )
            for record in self
        )
        self.invalidate_recordset(["reservation_ids", "schedule_overlap_count"])

    def _active_for_sync(self) -> Self:
        if "active" in self._fields:
            return self.filtered("active")
        return self
