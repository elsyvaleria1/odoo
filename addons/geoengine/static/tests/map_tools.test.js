/** @odoo-module native */

import {
    formatArea,
    formatLength,
} from "@geoengine/geoengine/renderer/geoengine_map_tools";
import { describe, expect, test } from "@odoo/hoot";

describe("formatLength", () => {
    test("reads metres below a kilometre, with no misleading precision", () => {
        expect(formatLength(0)).toBe("0 m");
        expect(formatLength(12.4)).toBe("12 m");
        expect(formatLength(999.6)).toBe("1000 m");
    });

    test("switches to kilometres at 1000 m", () => {
        expect(formatLength(1000)).toBe("1.00 km");
        expect(formatLength(1240)).toBe("1.24 km");
        expect(formatLength(41000)).toBe("41.00 km");
    });
});

describe("formatArea", () => {
    test("reads square metres below a hectare", () => {
        expect(formatArea(0)).toBe("0 m²");
        expect(formatArea(9999)).toBe("9999 m²");
    });

    test("reads hectares between a hectare and a square kilometre", () => {
        expect(formatArea(1e4)).toBe("1.00 ha");
        expect(formatArea(34000)).toBe("3.40 ha");
        expect(formatArea(999999)).toBe("100.00 ha");
    });

    test("switches to square kilometres at 1 km²", () => {
        expect(formatArea(1e6)).toBe("1.00 km²");
        expect(formatArea(12.5e6)).toBe("12.50 km²");
    });
});
