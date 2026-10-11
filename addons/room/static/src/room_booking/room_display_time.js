/** @odoo-module native */
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { useInterval } from "@room/room_booking/useInterval";
import { formatValue, now } from "@web/core/l10n/dates";

export class RoomDisplayTime extends Component {
    static template = xml`<div class="d-flex flex-column justify-content-center"><span class="display-6" t-out="this.format(this.state.currentTime, 'T')"/><span class="smaller" t-out="this.format(this.state.currentTime, 'DDDD')"/></div>`;
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ currentTime: now() });
        useInterval(() => (this.state.currentTime = now()), 1000);
    }

    format(value, format) {
        return formatValue(value, format);
    }
}
