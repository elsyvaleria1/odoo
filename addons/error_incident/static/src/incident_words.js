// @ts-check
/** @odoo-module native */

/* Every sentence the dialog shows about an incident. The server sends ids
 * only; this is the one file the translators touch. */

import { _t } from "@web/core/translation";

/** @param {string} id */
export function stepLabel(id) {
    switch (id) {
        case "recorded":
            return _t("Recorded");
        case "acknowledged":
            return _t("A developer is on it");
        case "resolved":
            return _t("Fixed");
        default:
            // A step this client has not been taught: the id beats a blank row.
            return id;
    }
}

/**
 * @param {import("@error_incident/incident_journey").JourneyState} journey
 */
export function journeyHeadline(journey) {
    if (journey.outcome === "set_aside") {
        return _t("Set aside");
    }
    switch (journey.step) {
        case "resolved":
            return _t("This error is fixed");
        case "acknowledged":
            return _t("A developer is working on this error");
        default:
            return journey.details.regressed
                ? _t("This error came back after a fix")
                : _t("This error was recorded");
    }
}

/**
 * @param {import("@error_incident/incident_journey").JourneyState} journey
 */
export function journeyNote(journey) {
    if (journey.outcome === "set_aside") {
        return _t("A developer decided not to fix it for now.");
    }
    if (journey.step === "recorded") {
        return journey.details.regressed
            ? _t("It is back in the developers' queue.")
            : _t(
                  "There is nothing for you to report: the developers have it, with your user and the time.",
              );
    }
    if (journey.step === "resolved") {
        return _t("If it still happens, it is recorded again and reopened.");
    }
    return null;
}

/** @param {number} count */
export function countText(count) {
    return _t("It has happened %s times.", count);
}
