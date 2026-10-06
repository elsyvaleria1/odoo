/** @odoo-module native */
import { deserializeDateTime, now } from "@web/core/l10n/dates";
import { SignalStore } from "@web/core/utils/reactive";

export class TimerReactive extends SignalStore {
    constructor(env) {
        super();
        this.orm = env.services.orm;
        this.resetTimer();
    }

    get toSeconds() {
        return (this.hours * 60 + this.minutes) * 60 + this.seconds;
    }

    get floatValue() {
        return this.toSeconds / 3600;
    }

    formatTime() {
        const hours = `${this.hours}`.padStart(2, "0");
        const minutes = `${this.minutes}`.padStart(2, "0");
        const seconds = `${this.seconds}`.padStart(2, "0");
        this.time = `${hours}:${minutes}:${seconds}`;
    }

    addHours(hours) {
        this.hours += hours;
    }

    addMinutes(minutes) {
        minutes += this.minutes;
        this.minutes = minutes % 60;
        this.addHours(Math.floor(minutes / 60));
    }

    addSeconds(seconds) {
        seconds += this.seconds;
        this.seconds = seconds % 60;
        this.addMinutes(Math.floor(seconds / 60));
    }

    computeOffset(serverTime) {
        this.serverOffset = Math.trunc(
            this.getElapsedMilliseconds(now(), serverTime) / 1000,
        );
    }

    setTimer(timeElapsed, timerStart, serverTime) {
        this.resetTimer();
        this.addFloatTime(timeElapsed);
        this.timeElapsed = this.toSeconds;
        if (!serverTime && this.serverOffset !== null) {
            serverTime = timerStart.add({ seconds: this.serverOffset ?? 0 });
        }
        if (timerStart && serverTime) {
            const dateStart = timerStart;
            const elapsed = this.getElapsedMilliseconds(dateStart, serverTime);
            this.addHours(Math.trunc(elapsed / 3_600_000));
            this.addMinutes(Math.trunc((elapsed % 3_600_000) / 60_000));
            this.addSeconds(Math.trunc((elapsed % 60_000) / 1000));
        } else if ((timerStart && !serverTime) || (!timerStart && serverTime)) {
            console.error(
                "Missing parameter: the timerStart or serverTime when one of them is defined.",
            );
        }
    }

    /**
     * @param {Temporal.ZonedDateTime} dateA
     * @param {Temporal.ZonedDateTime} dateB
     * @returns {number}
     */
    getElapsedMilliseconds(dateA, dateB) {
        return Math.abs(dateB.epochMilliseconds - dateA.epochMilliseconds);
    }

    getCurrentTime() {
        return now().add({ seconds: this.serverOffset ?? 0 });
    }

    async getServerTime() {
        const serverTime = deserializeDateTime(
            await this.orm.call("timer.timer", "get_server_time"),
        );
        return serverTime.withTimeZone("UTC");
    }

    addFloatTime(timeElapsed) {
        if (timeElapsed === 0) {
            this.hours = this.minutes = this.seconds = 0;
            return;
        }

        const minutes = timeElapsed % 1;
        this.hours = timeElapsed - minutes;
        this.minutes = minutes * 60;
    }

    updateTimer(timerStart) {
        const currentTime = this.getCurrentTime();
        const seconds = Math.trunc(
            this.getElapsedMilliseconds(timerStart, currentTime) / 1000,
        );
        this.addSeconds(seconds - this.toSeconds + this.timeElapsed);
    }

    resetTimer() {
        this.hours = 0;
        this.minutes = 0;
        this.seconds = 0;
        this.time = "";
    }
}
