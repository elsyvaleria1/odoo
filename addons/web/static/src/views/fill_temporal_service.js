// @ts-check
/** @odoo-module native */
import {
    areDatesEqual,
    isDateValue,
    maxDate,
    now,
    serializeDate,
    serializeDateTime,
    startOf,
    today,
} from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";

/**
 * @typedef {Temporal.ZonedDateTime | Temporal.PlainDate} DateTime
 * @typedef {{ name: string, type: "date" | "datetime" }} TemporalField
 * @typedef {{
 *     startOf: (dt: DateTime) => DateTime,
 *     cycle: number,
 *     cyclePos: (dt: DateTime) => number,
 * }} GranularityConfig
 * @typedef {{
 *     min_groups: number,
 *     fill_from?: string | false,
 *     fill_to?: string | false,
 * }} FillTemporalContext
 */

/** @type {Record<string, GranularityConfig>} */
export const GRANULARITY_TABLE = {
    hour: {
        startOf: (x) => startOf(x, "hour"),
        cycle: 24,
        cyclePos: (x) => /** @type {Temporal.ZonedDateTime} */ (x).hour + 1,
    },
    day: {
        startOf: (x) => startOf(x, "day"),
        cycle: 7,
        cyclePos: (x) => x.dayOfWeek,
    },
    week: {
        startOf: (x) => startOf(x, "week"),
        cycle: 1,
        cyclePos: () => 1,
    },
    month: {
        startOf: (x) => startOf(x, "month"),
        cycle: 12,
        cyclePos: (x) => x.month,
    },
    quarter: {
        startOf: (x) => startOf(x, "quarter"),
        cycle: 4,
        cyclePos: (x) => Math.ceil(x.month / 3),
    },
    year: {
        startOf: (x) => startOf(x, "year"),
        cycle: 1,
        cyclePos: () => 1,
    },
};

const DEFAULT_MIN_GROUPS = 4;

/**
 * @param {DateTime} date
 * @param {string} granularity
 * @param {number} count
 * @returns {DateTime}
 */
function addGranularity(date, granularity, count) {
    return granularity === "quarter"
        ? date.add({ months: 3 * count })
        : date.add({ [`${granularity}s`]: count });
}

export class FillTemporalPeriod {
    /** @type {DateTime} */
    start;

    /** @type {DateTime} */
    end;

    /** @type {boolean} */
    computedEnd;

    /** @type {number} */
    minGroups;

    /**
     * @param {string} modelName
     * @param {TemporalField} field
     * @param {string} granularity
     * @param {number} minGroups
     */
    constructor(modelName, field, granularity, minGroups) {
        this.modelName = modelName;
        this.field = field;
        this.granularity = granularity || "month";
        this.setMinGroups(minGroups);

        this._computeStart();
        this._computeEnd();
    }
    /**
     * @private
     * @returns {DateTime}
     */
    _now() {
        return this.field.type === "date" ? today() : now();
    }
    /** @private */
    _computeStart() {
        this.start = GRANULARITY_TABLE[this.granularity].startOf(this._now());
    }
    /** @private */
    _computeEnd() {
        const cycle = GRANULARITY_TABLE[this.granularity].cycle;
        const cyclePos = GRANULARITY_TABLE[this.granularity].cyclePos(this.start);
        const fillTemporalPeriod =
            ((2 * cycle - ((this.minGroups - 1) % cycle) - cyclePos) % cycle) +
            this.minGroups;
        this.end = addGranularity(this.start, this.granularity, fillTemporalPeriod);
        this.computedEnd = true;
    }
    /**
     * @param {DateTime} bound
     * @returns {string | false}
     */
    _getFormattedServerDate(bound) {
        return isDateValue(bound) ? serializeDate(bound) : serializeDateTime(bound);
    }
    /**
     * @param {Object} configuration
     * @param {any[]} configuration.domain
     * @param {boolean} [configuration.forceStartBound=true]
     * @param {boolean} [configuration.forceEndBound=true]
     * @returns {any[]}
     */
    getDomain({ domain, forceStartBound = true, forceEndBound = true }) {
        if (!forceEndBound && !forceStartBound) {
            return domain;
        }
        const originalDomain = domain.length ? ["&", ...domain] : [];
        const defaultDomain = ["|", [this.field.name, "=", false]];
        const linkDomain = forceStartBound && forceEndBound ? ["&"] : [];
        const startDomain = !forceStartBound
            ? []
            : [[this.field.name, ">=", this._getFormattedServerDate(this.start)]];
        const endDomain = !forceEndBound
            ? []
            : [[this.field.name, "<", this._getFormattedServerDate(this.end)]];
        return [
            ...originalDomain,
            ...defaultDomain,
            ...linkDomain,
            ...startDomain,
            ...endDomain,
        ];
    }
    /**
     * @param {Object} configuration
     * @param {Object} [configuration.context]
     * @param {boolean} [configuration.forceFillingFrom=true]
     * @param {boolean} [configuration.forceFillingTo=!this.computedEnd]
     * @returns {Record<string, any> & { fill_temporal: FillTemporalContext }}
     */
    getContext({
        context,
        forceFillingFrom = true,
        forceFillingTo = !this.computedEnd,
    }) {
        /** @type {FillTemporalContext} */
        const fillTemporal = {
            min_groups: this.minGroups,
        };
        if (forceFillingFrom) {
            fillTemporal.fill_from = this._getFormattedServerDate(this.start);
        }
        if (forceFillingTo) {
            const minGranularity = this.field.type === "date" ? "days" : "seconds";
            fillTemporal.fill_to = this._getFormattedServerDate(
                this.end.subtract({ [minGranularity]: 1 }),
            );
        }
        return { ...context, fill_temporal: fillTemporal };
    }
    /** @param {number} minGroups */
    setMinGroups(minGroups) {
        const next = minGroups || 1;
        if (next === this.minGroups) {
            return;
        }
        this.minGroups = next;
        if (this.computedEnd) {
            this._computeEnd();
        }
    }
    /** @param {DateTime} end */
    setEnd(end) {
        this.end = maxDate(this.start, end);
        this.computedEnd = false;
    }
    /** @returns {boolean} */
    refreshStart() {
        const start = GRANULARITY_TABLE[this.granularity].startOf(this._now());
        if (areDatesEqual(start, this.start)) {
            return false;
        }
        this.start = start;
        if (this.computedEnd) {
            this._computeEnd();
        } else {
            this.end = maxDate(this.start, this.end);
        }
        return true;
    }
    expand() {
        this.setEnd(addGranularity(this.end, this.granularity, 1));
    }
}

export class FillTemporal {
    constructor() {
        /** @type {Map<string, FillTemporalPeriod>} */
        this._fillTemporalPeriods = new Map();
    }

    /**
     * @param {Object} configuration
     * @param {string} configuration.modelName
     * @param {TemporalField} configuration.field
     * @param {string} configuration.granularity
     * @param {number} [configuration.minGroups]
     * @param {boolean} [configuration.forceRecompute=false]
     * @returns {FillTemporalPeriod}
     */
    getFillTemporalPeriod({
        modelName,
        field,
        granularity,
        minGroups,
        forceRecompute = false,
    }) {
        const key = JSON.stringify([modelName, field.name, granularity]);
        let period = this._fillTemporalPeriods.get(key);
        if (!period || forceRecompute) {
            period = new FillTemporalPeriod(
                modelName,
                field,
                granularity,
                minGroups ?? DEFAULT_MIN_GROUPS,
            );
            this._fillTemporalPeriods.set(key, period);
            return period;
        }
        if (minGroups !== undefined) {
            period.setMinGroups(minGroups);
        }
        period.refreshStart();
        return period;
    }

    /**
     * @param {Object} configuration
     * @param {string} configuration.modelName
     * @param {string} configuration.groupBySpec
     * @param {Record<string, any>} configuration.fields
     * @param {number} [configuration.minGroups]
     * @param {boolean} [configuration.forceRecompute]
     * @returns {FillTemporalPeriod}
     */
    getFillTemporalPeriodForGroupBy({
        modelName,
        groupBySpec,
        fields,
        minGroups,
        forceRecompute,
    }) {
        const [fieldName, granularity] = groupBySpec.split(":");
        const { name, type } = fields[fieldName];
        return this.getFillTemporalPeriod({
            modelName,
            field: { name, type },
            granularity: granularity || "month",
            minGroups,
            forceRecompute,
        });
    }
}

export const fillTemporalService = {
    /** @returns {FillTemporal} */
    start() {
        return new FillTemporal();
    },
};

registry.category("services").add("fillTemporalService", fillTemporalService);
