import { expect } from "@odoo/hoot";
import { Domain } from "@web/core/domain";
import { diff, endOf, parseFormatted, parseISO } from "@web/core/l10n/dates";

function getDateDomainBounds(domain) {
    const startDateStr = domain[1][2];
    const endDateStr = domain[2][2];

    const isDateTime = startDateStr.includes(":");

    if (isDateTime) {
        const dateTimeFormat = "yyyy-MM-dd HH:mm:ss";
        const start = parseFormatted(startDateStr, dateTimeFormat);
        const end = parseFormatted(endDateStr, dateTimeFormat);
        return { start, end };
    }

    const start = parseISO(startDateStr);
    const end = parseISO(endDateStr);
    const startIsIncluded = domain[1][1] === ">=";
    const endIsIncluded = domain[2][1] === "<=";
    return {
        start: startIsIncluded ? start.startOfDay() : endOf(start, "day"),
        end: endIsIncluded ? endOf(end, "day") : end.startOfDay(),
    };
}

/**
 * @param {string} field
 * @param {string} start
 * @param {string} end
 * @param {import("@web/core/domain").DomainRepr} domain
 */
export function assertDateDomainEqual(field, start, end, domain) {
    domain = new Domain(domain).toList();
    expect(domain[0]).toBe("&");
    expect(domain[1]).toEqual([field, ">=", start]);
    expect(domain[2]).toEqual([field, "<=", end]);
}

/**
 * @param {import("@web/core/domain").DomainRepr} domain
 * @returns {number}
 */
export function getDateDomainDurationInDays(domain) {
    domain = new Domain(domain).toList();
    const bounds = getDateDomainBounds(domain);
    return Math.round(diff(bounds.end, bounds.start, "days"));
}
