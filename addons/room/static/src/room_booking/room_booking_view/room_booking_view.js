/** @odoo-module native */
import {
    Component,
    markup,
    onWillStart,
    onWillUnmount,
    proxy,
    t,
    useListener,
    useProps,
} from "@odoo/owl";
import {
    makeInterval,
    RoomBookingForm,
} from "@room/room_booking/room_booking_form/room_booking_form";
import { useBusChannel, useBusSubscription } from "@bus/services/bus_service";
import { RoomBookingRemainingTime } from "@room/room_booking/room_booking_remaining_time";
import { RoomDisplayTime } from "@room/room_booking/room_display_time";
import { useInterval } from "@room/room_booking/useInterval";
import { browser } from "@web/core/browser/browser";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import {
    compareDates,
    DATE_HUGE,
    deserializeDateTime,
    now,
    serializeDateTime,
    TIME_SIMPLE,
    toDate,
    today,
    toLocaleString,
    toRelativeCalendar,
} from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { redirect } from "@web/core/utils/urls";
import { ConfirmationDialog } from "@web/ui/dialog";

// Time (in ms, so 2 minutes) after which the user is considered inactive
// and the app goes back to the main screen
export const INACTIVITY_TIMEOUT = 120000;
export const REFRESH_INTERVAL = 1000;

/**
 * Format a booking received from the server to the format used in the room booking view
 * @param {Object} booking
 * @param {Number} booking.id
 * @param {String} booking.name
 * @param {Boolean} [booking.private] the server withholds its name
 * @param {String} booking.start_datetime
 * @param {String} booking.stop_datetime
 * @param {Boolean} [booking.readonly] a reservation from another origin (maintenance)
 */
function formatServerBooking(booking) {
    return {
        id: booking.id,
        name: booking.private ? _t("Busy") : booking.name,
        readonly: Boolean(booking.readonly),
        interval: makeInterval(
            deserializeDateTime(booking.start_datetime),
            deserializeDateTime(booking.stop_datetime),
        ),
    };
}

export class RoomBookingView extends Component {
    static components = {
        RoomBookingForm,
        RoomBookingRemainingTime,
        RoomDisplayTime,
    };
    static template = "room.RoomBookingView";
    static props = {
        accessToken: t.string(),
        bookableBgColor: t.string(),
        bookedBgColor: t.string(),
        busChannel: t.string(),
        description: t.string(),
        id: t.number(),
        name: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.manageRoomUrl = `/room/${this.props.accessToken}`;
        this.pwaService = useService("pwa");
        this.state = proxy({
            bookings: [],
            bookingName: undefined,
            bookingToEdit: undefined,
            currentBooking: null,
            currentDate: today(),
            scheduleBooking: false,
            scheduleBookingQuickCreate: false,
            showInstallPwaButton:
                !isDisplayStandalone() && this.pwaService.isSupportedOnBrowser,
        });
        // Show bookings updates in live
        useBusChannel(this.props.busChannel);
        useBusSubscription(`room#${this.props.id}/booking/create`, (bookings) =>
            bookings.forEach((booking) =>
                this.addBooking(formatServerBooking(booking)),
            ),
        );
        useBusSubscription(`room#${this.props.id}/booking/delete`, (bookings) =>
            bookings.forEach((booking) => this.removeBooking(booking.id)),
        );
        useBusSubscription(`room#${this.props.id}/booking/update`, (bookings) =>
            bookings.forEach((booking) =>
                this.updateBooking(formatServerBooking(booking)),
            ),
        );
        useBusSubscription(`room#${this.props.id}/reload`, (url) => redirect(url));
        this.notificationService = useService("notification");
        this.dialogService = useService("dialog");
        this.ui = useService("ui");
        onWillStart(this.loadBookings);

        // Every second, check if a booking started/ended
        useInterval(this.refreshBookingView.bind(this), REFRESH_INTERVAL);

        // If the user is inactive for more than the  INACTIVITY_TIMEOUT, reset the view
        ["pointerdown", "keydown"].forEach((event) =>
            useListener(window, event, () => {
                browser.clearTimeout(this.inactivityTimer);
                this.inactivityTimer = browser.setTimeout(() => {
                    this.resetBookingForm();
                }, INACTIVITY_TIMEOUT);
            }),
        );
        onWillUnmount(() => browser.clearTimeout(this.inactivityTimer));
    }

    // Formats

    get timeFormat() {
        return TIME_SIMPLE;
    }

    get dateFormat() {
        return DATE_HUGE;
    }

    formatLocalized(value, options) {
        return toLocaleString(value, options);
    }

    formatRelativeCalendar(value) {
        return toRelativeCalendar(value);
    }

    startsAfter(value, other) {
        return compareDates(value, other) > 0;
    }

    dayOf(value) {
        return toDate(value);
    }

    startsAfterMinutes(booking, minutes) {
        return compareDates(booking.interval.start, this.now.add({ minutes })) > 0;
    }

    // Getters

    /**
     * Return the background color of the main view which depends on the
     * room's availability
     */
    get bgColor() {
        return (
            (this.state.currentBooking
                ? this.props.bookedBgColor
                : this.props.bookableBgColor) + "DD"
        );
    }

    /**
     * Return the next booking
     * @returns {Object} booking
     */
    get nextBooking() {
        return this.state.currentBooking
            ? this.state.bookings[1]
            : this.state.bookings[0];
    }

    get now() {
        return now();
    }

    /**
     * @returns {string} Raw HTML of the description
     */
    get roomDescription() {
        return markup(this.props.description);
    }

    // Methods

    /**
     * Shows a confirmation dialog to delete the given booking
     * @param {Number} bookingId
     */
    deleteBooking(bookingId) {
        this.dialogService.add(ConfirmationDialog, {
            body: _t("Are you sure you want to delete this booking?"),
            confirmLabel: _t("Delete"),
            confirm: () => rpc(`${this.manageRoomUrl}/booking/${bookingId}/delete`),
            cancel: () => {},
        });
    }

    /**
     * Edit the given booking with the given values
     * @param {Number} bookingId
     * @param {String} name
     * @param {Temporal.ZonedDateTime} start
     * @param {Temporal.ZonedDateTime} end
     */
    async editBooking(bookingId, name, start, end) {
        this.ui.block();
        await rpc(`${this.manageRoomUrl}/booking/${bookingId}/update`, {
            name,
            start_datetime: serializeDateTime(start),
            stop_datetime: serializeDateTime(end),
        });
        this.removeBooking(bookingId);
        this.addBooking({
            id: bookingId,
            interval: makeInterval(start, end),
            name,
        });
        this.ui.unblock();
        this.resetBookingForm();
    }

    endCurrentBooking() {
        this.dialogService.add(ConfirmationDialog, {
            body: _t("Are you sure you want to end the current booking ?"),
            confirmLabel: _t("End Booking"),
            confirm: () => {
                const { id, name, interval } = this.state.currentBooking;
                this.editBooking(id, name, interval.start, this.now);
            },
            cancel: () => {},
        });
    }

    installPwa() {
        browser.open(
            `/scoped_app?app_id=room&path=${encodeURIComponent(browser.location.pathname.slice(1))}&app_name=${encodeURIComponent(this.props.name)}`,
        );
    }

    /**
     * Load the existing bookings for the room.
     * New bookings will be received through the busService.
     */
    async loadBookings() {
        const bookings = await rpc(`${this.manageRoomUrl}/get_existing_bookings`);
        for (const booking of bookings) {
            this.addBooking(formatServerBooking(booking));
        }
        this.refreshBookingView();
    }

    /**
     * Book the room for the given duration
     * @param {Number} duration (in minutes)
     */
    quickCreateBooking(duration) {
        this.scheduleBooking(
            this.state.bookingName,
            this.now,
            this.now.add({ minutes: duration }),
        );
    }

    /**
     * Update the current status of the room (booked or available), and remove
     * the booking of the list of bookings if it is finished.
     */
    refreshBookingView() {
        // Check if current booking is finished
        if (
            this.state.currentBooking &&
            compareDates(this.state.currentBooking.interval.end, this.now) < 0
        ) {
            this.removeBooking(this.state.currentBooking.id);
        }
        const currentBooking =
            this.state.bookings[0] &&
            compareDates(this.state.bookings[0].interval.start, this.now) < 0
                ? this.state.bookings[0]
                : null;
        // Check if next booking has started or if current booking has been rescheduled
        if (this.state.currentBooking?.interval.end !== currentBooking?.interval.end) {
            this.state.currentBooking = currentBooking;
        }
        // Update the currentDate that is used in the sidebar
        if (!this.state.currentDate.equals(toDate(this.now))) {
            this.state.currentDate = toDate(this.now);
        }
    }

    /**
     * Get back to the main view
     */
    resetBookingForm() {
        this.state.scheduleBooking = false;
        this.state.scheduleBookingQuickCreate = false;
        this.state.bookingToEdit = undefined;
        this.state.bookingName = undefined;
    }

    /**
     * Schedule a booking for the given time range, and reset the view to the main screen
     * @param {String} name
     * @param {Temporal.ZonedDateTime} start
     * @param {Temporal.ZonedDateTime} end
     */
    async scheduleBooking(name, start, end) {
        name = name || _t("Public Booking");
        this.ui.block();
        const bookingId = await rpc(`${this.manageRoomUrl}/booking/create`, {
            name,
            start_datetime: serializeDateTime(start),
            stop_datetime: serializeDateTime(end),
        });
        this.addBooking({
            id: bookingId,
            interval: makeInterval(start, end),
            name,
        });
        this.ui.unblock();
        this.resetBookingForm();
    }

    // Bus Methods

    /**
     * Add a booking to the list of bookings, keeping the list sorted by start date
     * @param {Object} newBooking
     * @param {Number} newBooking.id
     * @param {String} newBooking.name
     * @param {{ start: Temporal.ZonedDateTime, end: Temporal.ZonedDateTime }} newBooking.interval
     */
    addBooking(newBooking) {
        // Do not add bookings already added or already finished
        if (
            this.state.bookings.map((booking) => booking.id).includes(newBooking.id) ||
            compareDates(newBooking.interval.end, this.now) < 0
        ) {
            return;
        }
        const newBookingInsertIdx = this.state.bookings.findIndex(
            (booking) =>
                compareDates(booking.interval.start, newBooking.interval.start) > 0,
        );
        if (newBookingInsertIdx === -1) {
            this.state.bookings.push(newBooking);
        } else {
            this.state.bookings.splice(newBookingInsertIdx, 0, newBooking);
        }
        // If the new booking has already started (eg. book now), refresh the view
        if (compareDates(newBooking.interval.start, this.now) < 0) {
            this.refreshBookingView();
        }
    }

    /**
     * Remove a booking from the list of bookings
     * @param {Number} bookingId
     */
    removeBooking(bookingId) {
        const bookingIdx = this.state.bookings.findIndex(
            (booking) => booking.id === bookingId,
        );
        if (bookingIdx !== -1) {
            this.state.bookings.splice(bookingIdx, 1);
            // Refresh view if the booking deleted was the current one
            if (this.state.currentBooking?.id === bookingId) {
                this.refreshBookingView();
            }
        }
        // Leave form view if booking being edited has been deleted or updated by another user
        if (this.state.bookingToEdit?.id === bookingId && !this.ui.isBlocked) {
            this.resetBookingForm();
            this.notificationService.add(
                _t("The booking you were editing has been updated or deleted."),
            );
        }
    }

    /**
     * Update the given booking with the new values. For simplicity, the existing booking
     * is replaced by the new one so that order is maintained if the start date changed.
     * @param {Object} booking
     * @param {Number} booking.id
     * @param {{ start: Temporal.ZonedDateTime, end: Temporal.ZonedDateTime }} booking.interval
     * @param {String} booking.name
     */
    updateBooking(booking) {
        this.removeBooking(booking.id);
        this.addBooking(booking);
    }
}

registry.category("public_components").add("room.room_booking_view", RoomBookingView);
