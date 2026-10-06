// @ts-check
/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { DateTimeInput } from "@web/components/datetime";
import { makeLogger } from "@web/core/debug/debug_logger";
import {
    now,
    startOf,
    toDateTime,
    today,
    toISO,
    toLocaleString,
} from "@web/core/l10n/dates";
import { Dialog } from "@web/ui/dialog";

const log = makeLogger("mail.scheduled_message");
export class ScheduledDateDialog extends Component {
    static template = "mail.ScheduledDateDialog";
    static props = {
        close: t.function(),
        isRemovable: t.boolean(),
        save: t.function(),
        scheduledDate: t.instanceOf(Temporal.ZonedDateTime).optional(),
    };
    static components = {
        DateTimeInput,
        Dialog,
    };
    props = useProps(this.constructor.props);

    setup() {
        const current = now();
        const currentDay = today();
        this.tomorrowMorning = toDateTime(currentDay.add({ days: 1 })).with({
            hour: 8,
        });
        this.tomorrowAfternoon = this.tomorrowMorning.with({ hour: 13 });
        this.mondayMorning = toDateTime(
            currentDay.add({ days: (1 - currentDay.dayOfWeek + 7) % 7 || 7 }),
        ).with({ hour: 8 });

        this.state = proxy({
            customDateTime: startOf(current.add({ hours: 1 }), "hour").add({
                minutes: Math.ceil(current.minute / 5) * 5,
            }),
            selectedOption: undefined,
        });

        if (
            !this.props.scheduledDate ||
            this.props.scheduledDate.equals(this.tomorrowMorning)
        ) {
            this.state.selectedOption = "morning";
        } else if (this.props.scheduledDate.equals(this.tomorrowAfternoon)) {
            this.state.selectedOption = "afternoon";
        } else if (this.props.scheduledDate.equals(this.mondayMorning)) {
            this.state.selectedOption = "monday";
        } else {
            this.state.selectedOption = "custom";
            this.state.customDateTime = this.props.scheduledDate;
        }
        /** @type {Intl.DateTimeFormatOptions} */
        this.dateTimeFormat = {
            day: "numeric",
            hour: "numeric",
            minute: "numeric",
            month: "short",
        };
    }

    get dateTimePickerProps() {
        return {
            minDate: now(),
            /** @param {Temporal.ZonedDateTime} value */
            onSelect: (value) => (this.state.customDateTime = value),
            type: "datetime",
            value: this.state.customDateTime,
            rounding: 1,
        };
    }

    /** @param {Temporal.ZonedDateTime} value */
    formatScheduledDate(value) {
        return toLocaleString(value, this.dateTimeFormat);
    }

    get scheduledDate() {
        if (this.state.selectedOption === "morning") {
            return this.tomorrowMorning;
        } else if (this.state.selectedOption === "afternoon") {
            return this.tomorrowAfternoon;
        } else if (this.state.selectedOption === "monday") {
            return this.mondayMorning;
        } else {
            return this.state.customDateTime;
        }
    }

    clear() {
        log.logic("clear");
        this.props.save(false);
        this.props.close();
    }

    save() {
        log.logic("save", () => ({ scheduledDate: toISO(this.scheduledDate) }));
        this.props.save(this.scheduledDate);
        this.props.close();
    }
}
