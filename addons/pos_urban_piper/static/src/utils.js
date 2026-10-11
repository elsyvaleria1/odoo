/** @odoo-module native */
import { formatDateTime, fromEpochMilliseconds } from "@web/core/l10n/dates";
export function getTime(time) {
    return formatDateTime(fromEpochMilliseconds(time));
}
