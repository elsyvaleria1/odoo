// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { formatDateTime, now } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { registerField } from "@web/fields/_registry";
import {
    SelectionField,
    selectionField,
} from "@web/fields/selection/selection/selection_field";

const log = makeLogger("web.field.timezone_mismatch");

export class TimezoneMismatchField extends SelectionField {
    static template = "web.TimezoneMismatchField";
    static props = {
        ...super.props,
        tzOffsetField: t.string().optional("tz_offset"),
        mismatchTitle: t
            .string()
            .optional(
                _t(
                    "Timezone Mismatch : This timezone is different from that of your browser.\nPlease, set the same timezone as your browser's to avoid time discrepancies in your system.",
                ),
            ),
    };

    /** @returns {number | null} minutes east of UTC, from the record's "+HHMM" offset */
    get recordOffset() {
        const match =
            this.props.record.data[this.props.tzOffsetField]?.match(
                /^([+-])(\d{2})(\d{2})$/,
            );
        if (!match) {
            return null;
        }
        const minutes = Number(match[2]) * 60 + Number(match[3]);
        return match[1] === "-" ? -minutes : minutes;
    }

    /** @returns {boolean} */
    get mismatch() {
        if (!this.field.value) {
            return true;
        }
        const recordOffset = this.recordOffset;
        return (
            recordOffset !== null && recordOffset !== -new Date().getTimezoneOffset()
        );
    }

    /** @returns {string} */
    get mismatchTitle() {
        if (!this.field.value) {
            return _t("Set a timezone on your user");
        }
        return this.props.mismatchTitle;
    }

    /** @returns {Array<[string, string]>} */
    get options() {
        const recordOffset = this.recordOffset;
        if (!this.mismatch || recordOffset === null) {
            return super.options;
        }
        // the default zone is the session user's, not necessarily the record's:
        // shift UTC by the record's offset and format it as UTC to get its wall clock.
        const recordNow = formatDateTime(now("UTC").add({ minutes: recordOffset }), {
            tz: "utc",
        });
        log.logic("mismatch label", () => ({
            recordOffset,
            browserOffset: -new Date().getTimezoneOffset(),
            recordNow,
        }));
        return super.options.map((/** @type {any} */ option) => {
            const [value, label] = option;
            return value === this.field.value
                ? [value, `${label} (${recordNow})`]
                : option;
        });
    }
}

const timezoneMismatchField = {
    ...selectionField,
    component: TimezoneMismatchField,
    additionalClasses: ["d-flex"],
    supportedOptions: [
        ...(selectionField.supportedOptions || []),
        {
            label: _t("Mismatch title"),
            name: "mismatch_title",
            type: "string",
        },
        {
            label: _t("Timezone offset field"),
            name: "tz_offset_field",
            type: "field",
            availableTypes: ["char"],
        },
    ],
    extractProps: (/** @type {any} */ fieldInfo, /** @type {any} */ dynamicInfo) => ({
        ...selectionField.extractProps(fieldInfo, dynamicInfo),
        tzOffsetField: fieldInfo.options.tz_offset_field,
        mismatchTitle: fieldInfo.options.mismatch_title,
    }),
    fieldDependencies: (/** @type {any} */ { options }) => [
        { name: options.tz_offset_field || "tz_offset", type: "char" },
    ],
};

registerField("timezone_mismatch", timezoneMismatchField);
