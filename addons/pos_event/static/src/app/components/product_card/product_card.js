/** @odoo-module native */
import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";
import { compareDates, now } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(ProductCard.prototype, {
    get displayRemainingSeats() {
        return Boolean(this.props.product.event_id);
    },
    get isEventMultiSlot() {
        return (
            Boolean(this.props.product.event_id) &&
            this.props.product.event_id.is_multi_slots
        );
    },
    get totalFutureSlots() {
        return (
            this.props.product.event_id?.event_slot_ids?.filter(
                (slot) =>
                    slot.start_datetime && compareDates(slot.start_datetime, now()) > 0,
            )?.length || 0
        );
    },
    get totalTicketSeats() {
        const event = this.props.product.event_id;
        const eventTickets = event?.event_ticket_ids;

        if (!eventTickets?.length) {
            return 0;
        }
        if (eventTickets?.some((ticket) => ticket.seats_max === 0)) {
            if (!event.seats_limited) {
                return 0;
            }
            return event.seats_available > 0 ? event.seats_available : -1;
        }
        if (event.seats_limited && !event.seats_max) {
            return -1;
        }
        return (
            eventTickets.reduce((acc, ticket) => acc + ticket.seats_available, 0) || -1
        );
    },
});
