/** @odoo-module native */
import { formatDateTime, fromEpochMilliseconds } from "@web/core/l10n/dates";
/**
 * This method converts time from milliseconds to the user's time zone.
 */
export function getTime(time) {
    return formatDateTime(fromEpochMilliseconds(time));
}
