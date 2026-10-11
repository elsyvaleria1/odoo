/** @odoo-module native */
import { Component, onWillUpdateProps, proxy, t, useProps, xml } from "@odoo/owl";
import { useInterval } from "@room/room_booking/useInterval";
import { now } from "@web/core/l10n/dates";

function millisecondsUntil(endTime) {
    return endTime.epochMilliseconds - now().epochMilliseconds;
}

function formatRemainingTime(milliseconds) {
    const seconds = Math.trunc(milliseconds / 1000);
    return [Math.trunc(seconds / 3600), Math.trunc(seconds / 60) % 60, seconds % 60]
        .map((part) => (part < 0 ? "-" : "") + String(Math.abs(part)).padStart(2, "0"))
        .join(":");
}

export class RoomBookingRemainingTime extends Component {
    static template = xml`
        <div class="o_room_remaining_time rounded py-3 bg-black-25 display-4 text-center text-white"
             t-out="this.formattedRemainingTime"/>
    `;
    static props = { endTime: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ remainingTime: millisecondsUntil(this.props.endTime) });
        useInterval(() => {
            const remainingTime = millisecondsUntil(this.props.endTime);
            if (remainingTime >= 0) {
                this.state.remainingTime = remainingTime;
            }
        }, 1000);
        onWillUpdateProps((nextProps) => {
            this.state.remainingTime = millisecondsUntil(nextProps.endTime);
        });
    }

    get formattedRemainingTime() {
        return formatRemainingTime(this.state.remainingTime);
    }
}
