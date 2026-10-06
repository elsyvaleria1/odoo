/** @odoo-module native */
import {
    classColorFor,
    classIndexFor,
    INTERVAL,
    isWebGLExpressible,
    legendHtml,
    QUANTILE,
    toRgbaString,
    UNIQUE,
    valueHash,
    withOpacity,
} from "@geoengine/geoengine/classification";
import { describe, expect, test } from "@odoo/hoot";

const INTERVAL_STYLING = {
    mode: INTERVAL,
    values: [0, 7395.75, 14791.5, 22187.25, 29583],
    colors: [
        "rgba(255, 104, 10, 0.8)",
        "rgba(170, 104, 10, 0.8)",
        "rgba(85, 104, 10, 0.8)",
        "rgba(0, 104, 10, 0.8)",
    ],
    legendLabels: [
        "0 - 7395.75",
        "7395.75 - 14791.5",
        "14791.5 - 22187.25",
        "22187.25 - 29583",
    ],
};

const UNIQUE_STYLING = {
    mode: UNIQUE,
    values: [0, 101, 1056, 112, 2880, 29583, 361],
    colors: ["c0", "c1", "c2", "c3", "c4", "c5", "c6"],
};

describe("classIndexFor - ranged", () => {
    test("puts each value in its own class, not all of them in class 0", () => {
        expect(classIndexFor(INTERVAL_STYLING, 0)).toBe(0);
        expect(classIndexFor(INTERVAL_STYLING, 7000)).toBe(0);
        expect(classIndexFor(INTERVAL_STYLING, 8000)).toBe(1);
        expect(classIndexFor(INTERVAL_STYLING, 20000)).toBe(2);
        expect(classIndexFor(INTERVAL_STYLING, 29583)).toBe(3);
    });

    test("classes are half-open at the upper bound", () => {
        expect(classIndexFor(INTERVAL_STYLING, 7395.75)).toBe(0);
        expect(classIndexFor(INTERVAL_STYLING, 7395.76)).toBe(1);
    });

    test("clamps outside the serie instead of dropping the feature", () => {
        expect(classIndexFor(INTERVAL_STYLING, -1)).toBe(0);
        expect(classIndexFor(INTERVAL_STYLING, 99999)).toBe(3);
    });

    test("a non-numeric value classifies into nothing", () => {
        expect(classIndexFor(INTERVAL_STYLING, "n/a")).toBe(-1);
        expect(classIndexFor(INTERVAL_STYLING, null)).toBe(-1);
    });

    test("quantile reads exactly like interval", () => {
        const quantile = { ...INTERVAL_STYLING, mode: QUANTILE };
        expect(classIndexFor(quantile, 20000)).toBe(2);
    });

    test("REGRESSION: range strings are not a usable `values`", () => {
        const broken = {
            mode: INTERVAL,
            values: INTERVAL_STYLING.legendLabels,
            colors: INTERVAL_STYLING.colors,
        };
        expect(classIndexFor(broken, 20000)).toBe(-1);
    });
});

describe("classIndexFor - unique", () => {
    test("matches on equality, not on ordering", () => {
        expect(classIndexFor(UNIQUE_STYLING, 361)).toBe(6);
        expect(classIndexFor(UNIQUE_STYLING, 1056)).toBe(2);
        expect(classIndexFor(UNIQUE_STYLING, 0)).toBe(0);
    });

    test("a value not among the categories classifies into nothing", () => {
        expect(classIndexFor(UNIQUE_STYLING, 999)).toBe(-1);
    });

    test("works for the non-numeric categories a Selection field produces", () => {
        const styling = { mode: UNIQUE, values: ["draft", "done"], colors: ["a", "b"] };
        expect(classIndexFor(styling, "done")).toBe(1);
    });
});

describe("classColorFor", () => {
    test("returns the class colour", () => {
        expect(classColorFor(INTERVAL_STYLING, 20000)).toBe("rgba(85, 104, 10, 0.8)");
    });

    test("returns null rather than defaulting to class 0", () => {
        expect(classColorFor(UNIQUE_STYLING, 999)).toBe(null);
    });

    test("survives an absent classification", () => {
        expect(classColorFor(null, 1)).toBe(null);
        expect(classColorFor({ mode: UNIQUE, values: [], colors: [] }, 1)).toBe(null);
    });
});

describe("isWebGLExpressible", () => {
    test("numeric classifications are expressible", () => {
        expect(isWebGLExpressible(INTERVAL_STYLING)).toBe(true);
        expect(isWebGLExpressible(UNIQUE_STYLING)).toBe(true);
    });

    test("a shader has no string type, so text categories are not", () => {
        expect(
            isWebGLExpressible({ mode: UNIQUE, values: ["draft", "done"], colors: [] }),
        ).toBe(false);
    });
});

describe("toRgbaString", () => {
    test("emits the one spelling both renderers parse", () => {
        const fakeChromaColor = { rgba: () => [255, 104.4, 10, 0.6] };
        expect(toRgbaString(fakeChromaColor)).toBe("rgba(255, 104, 10, 0.6)");
    });
});

describe("legendHtml", () => {
    test("escapes the layer name and every label, so a record value cannot inject markup", () => {
        const html = legendHtml(
            "Machines <b>by band</b>",
            ['<img src=x onerror="window.__xss=1">', "0 - 10"],
            ["rgba(1, 2, 3, 1)", "rgba(4, 5, 6, 1)"],
        );
        expect(html).not.toInclude("<img");
        expect(html).not.toInclude("<b>");
        expect(html).toInclude("&lt;img src=x onerror=");
        expect(html).toInclude("geostats-legend-title");
        expect(html.match(/geostats-legend-block/g)).toHaveLength(2);
        expect(html).toInclude("background-color:rgba(4, 5, 6, 1)");
    });
});

describe("withOpacity", () => {
    test("scales rgba, converts hex, leaves the rest alone", () => {
        expect(withOpacity("rgba(51, 136, 255, 1)", 0.5)).toBe(
            "rgba(51, 136, 255, 0.5)",
        );
        expect(withOpacity("rgb(1, 2, 3)", 0.25)).toBe("rgba(1, 2, 3, 0.25)");
        expect(withOpacity("#3388ff", 0.5)).toBe("rgba(51, 136, 255, 0.5)");
        expect(withOpacity("#fff", 0.2)).toBe("rgba(255, 255, 255, 0.2)");
        expect(withOpacity("#3388ff", 1)).toBe("#3388ff");
        expect(withOpacity("tomato", 0.5)).toBe("tomato");
        expect(withOpacity(undefined, 0.5)).toBe(undefined);
    });
});

describe("valueHash", () => {
    test("distinguishes texts of equal length and keeps numbers as themselves", () => {
        expect(valueHash("AB")).not.toBe(valueHash("CD"));
        expect(valueHash("AB")).toBe(valueHash("AB"));
        expect(valueHash(42)).toBe(42);
        expect(valueHash("42")).toBe(42);
    });
});
