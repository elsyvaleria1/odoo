/** @odoo-module native */
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils";
import { Component, t, useProps } from "@odoo/owl";
import {
    DATE_FULL,
    DATETIME_MED,
    isDateValue,
    parseISO,
    TIME_SIMPLE,
    toDate,
    toISO,
    toLocaleString,
} from "@web/core/l10n/dates";

/**
 * A "date" chip stores its day ("2026-04-05"); a "datetime" or "time" chip its
 * instant in UTC. A date chip stored as an instant, as they were before, is the
 * day that instant falls on for the reader.
 *
 * @param {string} text
 * @param {string} type
 * @returns {Temporal.PlainDate | Temporal.ZonedDateTime | null}
 */
export function readEmbeddedDate(text, type) {
    const value = parseISO(text);
    return value && type === "date" ? toDate(value) : value;
}

/**
 * @param {Temporal.PlainDate | Temporal.ZonedDateTime} value
 * @returns {string}
 */
export function writeEmbeddedDate(value) {
    return isDateValue(value) ? toISO(value) : toISO(value.withTimeZone("UTC"));
}

export class ReadonlyEmbeddedDateComponent extends Component {
    static template = "html_editor.ReadonlyEmbeddedDate";
    static props = {
        host: t.instanceOf(HTMLElement),
        date: t.string(),
        type: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.DATE_FORMATS = {
            datetime: DATETIME_MED,
            date: DATE_FULL,
            time: TIME_SIMPLE,
        };
    }

    get date() {
        return this.props.date;
    }

    get formattedDate() {
        const date = readEmbeddedDate(this.date, this.props.type);
        return date ? toLocaleString(date, this.DATE_FORMATS[this.props.type]) : "";
    }
}

export const readonlyDateEmbedding = {
    name: "date",
    Component: ReadonlyEmbeddedDateComponent,
    getProps: (host) => ({ host, ...getEmbeddedProps(host) }),
};
