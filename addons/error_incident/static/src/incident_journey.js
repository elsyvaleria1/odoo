// @ts-check
/** @odoo-module native */

import {
    countText,
    journeyHeadline,
    journeyNote,
    stepLabel,
} from "@error_incident/incident_words";
import { onWillDestroy, proxy } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { rpc } from "@web/core/network";
import { useService } from "@web/core/utils/hooks";

const log = makeLogger("error_incident");

export const JOURNEY_NOTIFICATION = "error_incident/journey";

/**
 * @typedef {Object} Journey
 * @property {number} incident
 * @property {string[]} steps
 * @property {string} step
 * @property {string | null} outcome
 * @property {{count: number, regressed: boolean}} details
 * @property {string} [occurrence]
 */

/**
 * @typedef {Object} JourneyState
 * @property {"idle" | "waiting" | "following"} stage
 * @property {number | null} incident
 * @property {string[]} steps
 * @property {string | null} step
 * @property {string | null} outcome
 * @property {{count: number, regressed: boolean}} details
 */

/**
 * @typedef {Object} BusService
 * @property {(type: string, callback: (payload: any) => void) => () => void} subscribe
 */

export class IncidentJourney {
    static RETRY_MS = [1500, 5000, 15000];

    /**
     * @param {string | null} occurrence
     * @param {BusService} bus
     */
    constructor(occurrence, bus) {
        this.occurrence = occurrence;
        this.bus = bus;
        /** @type {JourneyState} */
        this.state = proxy({
            stage: "idle",
            incident: null,
            steps: [],
            step: null,
            outcome: null,
            details: { count: 0, regressed: false },
        });
        this.alive = true;
        this.timer = null;
        /** @type {(() => void) | null} */
        this.stopListening = null;
        this.onNotification = (/** @type {Journey} */ journey) => this.receive(journey);
    }

    start() {
        if (!this.occurrence) {
            return;
        }
        this.state.stage = "waiting";
        this.listen();
        this.ask(0);
    }

    /** @param {number} attempt */
    async ask(attempt) {
        let answer = null;
        try {
            answer = await rpc(
                "/error_incident/journey",
                { occurrence: this.occurrence },
                { silent: true },
            );
        } catch {}
        log.logic("ask", this.occurrence, attempt, answer?.state);
        if (!this.alive || this.state.stage !== "waiting") {
            return;
        }
        if (answer?.state === "found") {
            this.apply(answer);
            return;
        }
        if (answer?.state === "unavailable") {
            this.state.stage = "idle";
            return;
        }
        const delay = IncidentJourney.RETRY_MS[attempt];
        if (delay === undefined) {
            log.logic("ask.give_up", this.occurrence);
            this.state.stage = "idle";
            return;
        }
        this.timer = setTimeout(() => this.ask(attempt + 1), delay);
    }





    async report(stack) {
        this.state.stage = "waiting";
        this.listen();
        let answer = null;
        try {
            answer = await rpc(
                "/error_incident/report",
                { stack, location: browser.location.pathname },
                { silent: true },
            );
        } catch {}
        log.logic("report", answer?.state, answer?.incident);
        if (!this.alive || this.state.stage !== "waiting") {
            return;
        }
        if (answer?.state === "found") {
            this.occurrence = answer.occurrence;
            this.apply(answer);
            return;
        }
        this.state.stage = "idle";
    }

    /** @param {Journey} journey */
    receive(journey) {
        const mine =
            (this.occurrence && journey.occurrence === this.occurrence) ||
            (this.state.incident !== null && journey.incident === this.state.incident);
        log.logic("receive", journey.incident, journey.step, mine);
        if (mine && this.alive) {
            this.apply(journey);
        }
    }

    /** @param {Journey} journey */
    apply(journey) {
        clearTimeout(this.timer);
        this.timer = null;
        Object.assign(this.state, {
            stage: "following",
            incident: journey.incident,
            steps: journey.steps,
            step: journey.step,
            outcome: journey.outcome,
            details: journey.details,
        });
    }

    listen() {
        this.stopListening ??= this.bus.subscribe(
            JOURNEY_NOTIFICATION,
            this.onNotification,
        );
    }

    destroy() {
        this.alive = false;
        clearTimeout(this.timer);
        this.stopListening?.();
    }

    get following() {
        return this.state.stage === "following";
    }

    get fixed() {
        return this.state.step === "resolved";
    }

    get headline() {
        return journeyHeadline(this.state);
    }

    get note() {
        return journeyNote(this.state);
    }

    get count() {
        const count = this.state.details.count;
        return count > 1 ? countText(count) : null;
    }

    get markClass() {
        if (this.state.outcome) {
            return "o_error_incident_dot o_error_incident_dot_stopped";
        }
        return this.fixed
            ? "o_error_incident_dot o_error_incident_dot_done"
            : "o_error_incident_dot";
    }

    get steps() {
        const reached = this.state.steps.indexOf(this.state.step ?? "");
        return this.state.steps.map((id, index) => {
            let state = "todo";
            if (index < reached || (index === reached && this.fixed)) {
                state = "done";
            } else if (index === reached) {
                state = this.state.outcome ? "stopped" : "active";
            }
            return {
                id,
                label: stepLabel(id),
                className: `o_error_incident_${state}`,
                current: index === reached,
            };
        });
    }
}

/** @param {string | null} occurrence */
export function useIncidentJourney(occurrence) {
    const journey = new IncidentJourney(occurrence, useService("bus_service"));
    onWillDestroy(() => journey.destroy());
    return journey;
}
