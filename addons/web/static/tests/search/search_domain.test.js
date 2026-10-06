// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { allowTranslations, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { parseISO } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import {
    computeDateFilterDescription,
    computeDateFilterDomain,
    computeDomain,
    computeGroupDomain,
} from "@web/search/search_domain";

describe.current.tags("headless");

const FIELDS = {
    owner_id: { type: "many2one" },
    tag_ids: { type: "many2many" },
    state: { type: "selection" },
};

/**
 * @param {string} fieldName
 * @param {Array<[any, Array<[any, boolean]>]>} groupEntries
 * @param {boolean} [enableCounters=true]
 */
function makeGroupedFilter(fieldName, groupEntries, enableCounters = true) {
    return {
        fieldName,
        enableCounters,
        groups: new Map(
            groupEntries.map(([groupId, values]) => [
                groupId,
                {
                    values: new Map(
                        values.map(([id, checked]) => [id, { id, checked }]),
                    ),
                },
            ]),
        ),
    };
}

describe("counters disabled or ungrouped", () => {
    test("many2one yields a neutral domain", () => {
        expect(
            computeGroupDomain(
                { fieldName: "owner_id", enableCounters: false, groups: null },
                FIELDS,
            ),
        ).toEqual([]);
    });

    test("many2many yields a neutral per-group map", () => {
        expect(
            computeGroupDomain(
                { fieldName: "tag_ids", enableCounters: false, groups: null },
                FIELDS,
            ),
        ).toEqual({});
    });
});

describe("selection fields", () => {
    test("ungrouped selection returns null, never undefined", () => {
        const result = computeGroupDomain(
            { fieldName: "state", enableCounters: false, groups: null },
            FIELDS,
        );
        expect(result).toBe(null);
    });

    test("grouped selection with counters returns null", () => {
        const filter = makeGroupedFilter("state", [
            [1, [["abc", true]]],
            [2, [["def", false]]],
        ]);
        expect(computeGroupDomain(filter, FIELDS)).toBe(null);
    });
});

describe("many2one", () => {
    test("one active group restricts to that group's values", () => {
        const filter = makeGroupedFilter("owner_id", [
            [
                1,
                [
                    [1, true],
                    [2, false],
                ],
            ],
            [2, [[3, false]]],
        ]);
        expect(computeGroupDomain(filter, FIELDS)).toEqual([
            ["owner_id", "in", [1, 2]],
        ]);
    });

    test("two active groups are mutually exclusive, so nothing matches", () => {
        const filter = makeGroupedFilter("owner_id", [
            [1, [[1, true]]],
            [2, [[3, true]]],
        ]);
        expect(computeGroupDomain(filter, FIELDS)).toEqual([[0, "=", 1]]);
    });

    test("no active group leaves the counts alone", () => {
        const filter = makeGroupedFilter("owner_id", [
            [1, [[1, false]]],
            [2, [[3, false]]],
        ]);
        expect(computeGroupDomain(filter, FIELDS)).toBe(null);
    });
});

describe("many2many", () => {
    test("each group is complemented by the OTHER groups' checked values", () => {
        const filter = makeGroupedFilter("tag_ids", [
            [1, [[10, true]]],
            [2, [[20, true]]],
        ]);
        expect(computeGroupDomain(filter, FIELDS)).toEqual({
            1: [["tag_ids", "in", [20]]],
            2: [["tag_ids", "in", [10]]],
        });
    });
});

describe("computeDomain — OR within a query group", () => {
    /**
     * @param {any[][]} itemDomainsByGroup
     */
    function domainOf(itemDomainsByGroup) {
        const groups = itemDomainsByGroup.map((itemDomains, groupIndex) => ({
            id: groupIndex,
            activeItems: itemDomains.map((domain) => ({ searchItemId: domain })),
        }));
        return computeDomain({
            groups,
            globalDomain: [],
            withGlobal: false,
            withSearchPanel: false,
            getSearchItemDomain: (/** @type {any} */ activeItem) =>
                activeItem.searchItemId,
            getSearchPanelDomain: () => [],
            domainEvalContext: {},
            raw: false,
        });
    }

    test("an item without a domain makes its group match everything", () => {
        expect(domainOf([["[]", "[('foo', '=', 'a')]"]])).toEqual([]);
        expect(domainOf([["[('foo', '=', 'a')]", []]])).toEqual([]);
    });

    test("other groups still AND in", () => {
        expect(
            domainOf([["[]", "[('foo', '=', 'a')]"], ["[('bar', '=', 1)]"]]),
        ).toEqual([["bar", "=", 1]]);
    });

    test("items with domains are OR'd", () => {
        expect(domainOf([["[('foo', '=', 'a')]", "[('foo', '=', 'b')]"]])).toEqual([
            "|",
            ["foo", "=", "a"],
            ["foo", "=", "b"],
        ]);
    });
});

describe("date filter domain and description", () => {
    test("share one construction per reference moment and generator ids", () => {
        patchWithCleanup(localization, { direction: "ltr" });
        allowTranslations();
        const referenceMoment = /** @type {Temporal.ZonedDateTime} */ (
            parseISO("2020-06-15T10:00:00")
        );
        const dateFilter = {
            type: "dateFilter",
            fieldName: "date_field",
            fieldType: "date",
            domain: "[]",
            optionsParams: {
                startYear: -2,
                endYear: 0,
                startMonth: -2,
                endMonth: 0,
                customOptions: [],
            },
        };
        const ids = ["month", "year"];

        const domain = computeDateFilterDomain(referenceMoment, dateFilter, ids);

        expect(computeDateFilterDomain(referenceMoment, dateFilter, [...ids])).toBe(
            domain,
        );
        expect(computeDateFilterDescription(referenceMoment, dateFilter, ids)).toBe(
            "June 2020",
        );
        expect(computeDateFilterDomain(referenceMoment, dateFilter, ["year"])).not.toBe(
            domain,
        );
        expect(
            computeDateFilterDomain(referenceMoment.add({ days: 1 }), dateFilter, ids),
        ).not.toBe(domain);
    });
});
