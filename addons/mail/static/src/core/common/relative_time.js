// @ts-check
/** @odoo-module native */
import {
    Component,
    onWillDestroy,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
    xml,
} from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { toRelative } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const NOW_THRESHOLD = 45 * 1000;

/**
 * @param {number} delta
 * @returns {number}
 */
export function computeUpdateDelay(delta) {
    const absDelta = Math.abs(delta);
    const cadence = absDelta < HOUR ? MINUTE : HOUR;
    let delay;
    if (delta < 0) {
        delay = Math.min(absDelta, cadence);
    } else if (absDelta < NOW_THRESHOLD) {
        delay = NOW_THRESHOLD - absDelta;
    } else {
        delay = cadence;
    }
    return Math.max(delay, 1);
}

export class RelativeTime extends Component {
    static props = { datetime: t.any() };
    static template = xml`<t t-out="this.state.relativeTime"/>`;
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.timeout = null;
        this.state = proxy({ relativeTime: "" });
        this.computeRelativeTime(this.props.datetime);
        onWillDestroy(() => browser.clearTimeout(this.timeout));
        onWillUpdateProps(
            /** @param {{datetime: Temporal.ZonedDateTime|undefined}} nextProps */ (
                nextProps,
            ) => {
                browser.clearTimeout(this.timeout);
                this.computeRelativeTime(nextProps.datetime);
            },
        );
    }

    /** @param {Temporal.ZonedDateTime|undefined} datetime */
    computeRelativeTime(datetime) {
        if (!datetime) {
            this.state.relativeTime = "";
            return;
        }
        const delta = Date.now() - datetime.epochMilliseconds;
        if (Math.abs(delta) < NOW_THRESHOLD) {
            this.state.relativeTime = delta < 0 ? _t("in a few seconds") : _t("now");
        } else {
            this.state.relativeTime = toRelative(datetime);
        }
        this.timeout = browser.setTimeout(() => {
            this.computeRelativeTime(this.props.datetime);
        }, computeUpdateDelay(delta));
    }
}
