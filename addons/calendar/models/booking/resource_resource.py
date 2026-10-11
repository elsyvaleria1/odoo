import logging
from typing import Self

from odoo import api, fields, models
from odoo.tools.translate import html_translate

_logger = logging.getLogger(__name__)

MAX_CAPACITY_COMBINATIONS = 4096


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    appointment_type_ids = fields.Many2many(
        comodel_name="appointment.type",
        relation="appointment_type_resource_rel",
        column1="resource_id",
        column2="appointment_type_id",
        string="Available in",
        domain="[('schedule_based_on', '=', 'resources')]",
    )
    is_bookable = fields.Boolean(
        compute="_compute_is_bookable",
        store=True,
        help="This resource is offered by at least one appointment type.",
    )
    booking_sequence = fields.Integer(
        default=1,
        required=True,
        help="Picked first when several resources fit the asked capacity (of two tables of 4, the lowest sequence goes first).",
    )
    booking_exclusive = fields.Boolean(
        default=True,
        help="A booking takes the whole resource, whatever capacity it asked for. Clear it to let several bookings share one time slot up to the capacity, as a bar counter does.",
    )
    source_resource_ids = fields.Many2many(
        comodel_name="resource.resource",
        relation="resource_combinable_resource_rel",
        column1="resource_id",
        column2="combinable_resource_id",
        string="Source combination",
        domain="[('id', '!=', id)]",
    )
    destination_resource_ids = fields.Many2many(
        comodel_name="resource.resource",
        relation="resource_combinable_resource_rel",
        column1="combinable_resource_id",
        column2="resource_id",
        string="Destination combination",
        domain="[('id', '!=', id)]",
    )
    combinable_resource_ids = fields.Many2many(
        comodel_name="resource.resource",
        compute="_compute_combinable_resource_ids",
        inverse="_inverse_combinable_resource_ids",
        store=False,
        domain="[('id', '!=', id)]",
        help="Resources that combine with this one to serve a bigger demand.",
    )
    description = fields.Html(
        translate=html_translate,
        sanitize_attributes=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        default_calendar = self.env.ref(
            "calendar.appointment_default_resource_calendar", raise_if_not_found=False
        )
        if default_calendar:
            for vals in vals_list:
                if vals.get("appointment_type_ids") and not vals.get("calendar_id"):
                    vals["calendar_id"] = default_calendar.id
        return super().create(vals_list)

    def _get_booking_picture(self) -> Self:
        self.check_singleton()
        return self.browse()

    @api.depends("appointment_type_ids")
    def _compute_is_bookable(self) -> None:
        for resource in self:
            resource.is_bookable = bool(resource.appointment_type_ids)

    @api.depends("source_resource_ids", "destination_resource_ids")
    def _compute_combinable_resource_ids(self) -> None:
        for resource in self:
            resource.combinable_resource_ids = (
                resource.source_resource_ids | resource.destination_resource_ids
            )

    def _inverse_combinable_resource_ids(self) -> None:
        for resource in self:
            actual_resources = resource.combinable_resource_ids
            current_resources = (
                resource.source_resource_ids | resource.destination_resource_ids
            )
            new_resources = actual_resources - current_resources
            old_resources = current_resources - actual_resources
            resource.source_resource_ids = (
                resource.source_resource_ids + new_resources - old_resources
            )
            resource.destination_resource_ids -= old_resources

    def _get_filtered_possible_capacity_combinations(
        self, asked_capacity, capacity_info
    ):
        capacities = {}
        for resource in self:
            capacities.update(
                resource._get_possible_capacity_combinations(capacity_info)
            )
        possible_capacities = {
            resource_ids: remaining_capacity
            for resource_ids, remaining_capacity in capacities.items()
            if remaining_capacity >= asked_capacity
            and all(resource_id in self.ids for resource_id in resource_ids)
        }
        return sorted(
            possible_capacities.items(),
            key=lambda possible_capacity: (
                possible_capacity[1],
                len(possible_capacity[0]),
            ),
        )

    def _get_possible_capacity_combinations(self, capacity_info):
        self.check_singleton()
        resource_remaining_capacity = capacity_info.get(self, {}).get(
            "remaining_capacity", self.capacity
        )
        capacities = {
            tuple(self.ids): resource_remaining_capacity,
        }
        for combinable_resource in self.combinable_resource_ids.sorted(
            "booking_sequence"
        ):
            if len(capacities) >= MAX_CAPACITY_COMBINATIONS:
                _logger.warning(
                    "resource.resource %s: capacity combination search capped at %s; "
                    "some combinable resources were not considered. Reduce the number of "
                    "mutually combinable resources on this appointment type.",
                    self.id,
                    MAX_CAPACITY_COMBINATIONS,
                )
                break
            capacities_to_add = {}
            for resource_ids, capacity in capacities.items():
                new_resource_ids = set(resource_ids)
                new_resource_ids.add(combinable_resource.id)
                combinable_resource_capacity = capacity_info.get(
                    combinable_resource, {}
                ).get("remaining_capacity", combinable_resource.capacity)
                capacities_to_add.update(
                    {
                        tuple(sorted(new_resource_ids)): capacity
                        + combinable_resource_capacity,
                    }
                )
            capacities.update(capacities_to_add)
        return capacities
