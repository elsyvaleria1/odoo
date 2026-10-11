// @ts-check

import { describe, expect, getFixture, test } from "@odoo/hoot";
import {
    blendColors,
    colorToRgb,
    convertCSSColorToRgba,
    convertRgbaToCSSColor,
    darkenColor,
    getColorBrightness,
    isCSSColor,
    lightenColor,
    mixCssColors,
    mixHexColors,
    mixRgbaColors,
    rgbaToHex,
    rgbToHex,
    withOpacity,
} from "@web/core/utils/format/colors";

describe.current.tags("headless");

test("opaque mixing preserves the kiosk weights and hex formats", () => {
    expect(mixHexColors("#fff", "000000", 0.5)).toBe("#808080");
    expect(mixHexColors("#ffffff", "#714B67", 0.95)).toBe("#f8f6f7");
    expect(mixHexColors("#000000", "#714B67", 0.6)).toBe("#2d1e29");
    expect(colorToRgb("#abc")).toBe("170, 187, 204");
    expect(colorToRgb("714B67")).toBe("113, 75, 103");
    expect(colorToRgb(" #abc ")).toBe("170, 187, 204");
    expect(mixHexColors(" #fff ", " 000000 ", 0.5)).toBe("#808080");
});

test("brightness uses the existing weighted channels and expands shorthand", () => {
    expect(getColorBrightness("#000")).toBe(0);
    expect(getColorBrightness("#fff")).toBeCloseTo(1);
    expect(getColorBrightness(" #fff ")).toBeCloseTo(1);
    expect(getColorBrightness("#f00")).toBeCloseTo(0.299);
    expect(getColorBrightness("#0f0")).toBeCloseTo(0.587);
    expect(getColorBrightness("#00f")).toBeCloseTo(0.114);
});

test("map opacity multiplies existing alpha without rounding it", () => {
    expect(withOpacity("rgba(10, 20, 30, 0.12345)", 0.5)).toBe(
        "rgba(10, 20, 30, 0.061725)",
    );
    expect(withOpacity("#abc", 0)).toBe("rgba(170, 187, 204, 0)");
    expect(withOpacity("rgb(1.5, 2, 3)", 0.25)).toBe("rgba(1.5, 2, 3, 0.25)");
    expect(withOpacity("tomato", 0.5)).toBe("tomato");
    expect(withOpacity("#abc", 1)).toBe("#abc");
});

describe("convertCSSColorToRgba", () => {
    test("reads a long alpha component whole", () => {
        expect(convertCSSColorToRgba("rgba(255,255,255,0.12345)")).toEqual({
            red: 255,
            green: 255,
            blue: 255,
            opacity: 12,
        });
        expect(convertCSSColorToRgba("rgb(12, 34, 56)")).toEqual({
            red: 12,
            green: 34,
            blue: 56,
            opacity: 100,
        });
    });

    test("reads an alpha written without its leading zero", () => {
        expect(convertCSSColorToRgba("rgba(1, 2, 3, .5)")).toEqual({
            red: 1,
            green: 2,
            blue: 3,
            opacity: 50,
        });
    });
});

describe("convertRgbaToCSSColor", () => {
    test("rounds fractional channels instead of writing them in hex", () => {
        expect(convertRgbaToCSSColor(10.5, 20.2, 29.8)).toBe("#0B141E");
        expect(convertRgbaToCSSColor(255.4, 0, 0, 50)).toBe("#FF000080");
        expect(convertRgbaToCSSColor(255.6, 0, 0)).toBe(false);
    });
});

describe("blendColors", () => {
    test("blends an alpha written without its leading zero", () => {
        expect(blendColors("rgba(0, 0, 0, .5)")).toBe("#808080");
    });

    test("blends the space-separated syntax and a fractional channel alike", () => {
        expect(blendColors("rgba(0 0 0 / .5)")).toBe("#808080");
        expect(blendColors("rgba(0.5, 0, 0, 0.5)")).toBe(
            blendColors("rgba(0, 0, 0, 0.5)"),
        );
        expect(rgbaToHex("rgba(16 32 48 / .25)")).toBe("#10203040");
    });
});

describe("rgbToHex", () => {
    test("blends a long alpha against the default white background", () => {
        expect(rgbToHex("rgba(10, 20, 30, 0.12345)")).toBe("#e1e2e3");
    });

    test("agrees with blendColors, which it now delegates to", () => {
        const fixture = /** @type {HTMLElement} */ (getFixture());
        const node = document.createElement("div");
        node.style.backgroundColor = "rgb(0, 0, 0)";
        fixture.appendChild(node);
        for (const color of [
            "rgba(255, 255, 255, 0.5)",
            "rgba(10, 20, 30, 0.12345)",
            "rgba(1, 2, 3, 0.7)",
        ]) {
            expect(rgbToHex(color, node)).toBe(blendColors(color, node));
        }
    });

    test("converts a plain rgb() color", () => {
        expect(rgbToHex("rgb(255, 0, 128)")).toBe("#ff0080");
    });
});

describe("rgbaToHex", () => {
    test("converts rgba() with alpha to an 8-digit hex", () => {
        expect(rgbaToHex("rgba(16, 32, 48, 0.5)")).toBe("#10203080");
        expect(rgbaToHex("rgba(16, 32, 48, .5)")).toBe("#10203080");
    });

    test("passes an uppercase hex color through unchanged", () => {
        expect(rgbaToHex("#ABCDEF")).toBe("#ABCDEF");
    });

    test("answers in one case whether the input is rgb(), rgba() or hex", () => {
        expect(rgbaToHex("rgb(255, 0, 128)")).toBe("#FF0080");
        expect(rgbaToHex("rgba(255, 0, 128, 1)")).toBe("#FF0080");
        expect(rgbaToHex("rgba(255, 0, 128, 0.5)")).toBe("#FF008080");
        expect(rgbaToHex("#ff0080")).toBe("#FF0080");
        expect(rgbaToHex("#f08")).toBe("#FF0088");
        expect(rgbaToHex("#ff008080")).toBe("#FF008080");
        const used = new Set(
            ["#ff0000", "#FF0000", "rgb(255, 0, 0)", "rgba(255, 0, 0, 1)"].map(
                (color) => rgbaToHex(color),
            ),
        );
        expect([...used]).toEqual(["#FF0000"]);
    });

    test("clamps an rgb() channel as CSS does, and answers '#' for a non-color", () => {
        expect(rgbaToHex("rgb(300, 0, 0)")).toBe("#FF0000");
        expect(rgbaToHex("rgba(0, 0, 0, 0)")).toBe("#00000000");
        expect(rgbaToHex("")).toBe("#");
        expect(rgbaToHex("tomato")).toBe("#");
        expect(rgbaToHex("#zzzzzz")).toBe("#");
    });
});

describe("colour mixing, as each caller formats it", () => {
    /** @param {string} bg */
    function kioskMixes(bg) {
        const light = getColorBrightness(bg) > 0.55;
        const text = light
            ? mixHexColors("#000000", bg, 0.95)
            : mixHexColors("#FFFFFF", bg, 0.95);
        return [
            colorToRgb(bg),
            mixHexColors("#000000", bg, 0.6),
            text,
            mixHexColors("#000000", bg, 0.2),
            colorToRgb(mixHexColors(text, bg, 0.15)),
            mixHexColors(text, bg, 0.85),
            mixHexColors("#ffffff", bg, 0.85),
        ];
    }

    test("pos_self_order kiosk: opaque lowercase hex, tolerant of bare and padded hex", () => {
        expect(kioskMixes("#714B67")).toEqual([
            "113, 75, 103",
            "#2d1e29",
            "#f8f6f7",
            "#5a3c52",
            "133, 101, 125",
            "#e4dce1",
            "#eae4e8",
        ]);
        expect(kioskMixes("#FFD700")).toEqual([
            "255, 215, 0",
            "#665600",
            "#0d0b00",
            "#ccac00",
            "219, 184, 0",
            "#312a00",
            "#fff9d9",
        ]);
        expect(kioskMixes("#F5F5DC")).toEqual([
            "245, 245, 220",
            "#626258",
            "#0c0c0b",
            "#c4c4b0",
            "210, 210, 189",
            "#2f2f2a",
            "#fefefa",
        ]);
        expect(kioskMixes("714B67")).toEqual(kioskMixes("#714B67"));
        expect(kioskMixes(" #2ca02c ")).toEqual([
            "44, 160, 44",
            "#124012",
            "#f4faf4",
            "#238023",
            "74, 174, 74",
            "#d6edd6",
            "#dff1df",
        ]);
        expect(kioskMixes("#abc")[1]).toBe("#444b52");
        expect(mixHexColors("#000000", "notacolor", 0.6)).toBe("notacolor");
    });

    /**
     * @param {string} color1
     * @param {string} color2
     */
    function configuratorPalette(color1, color2) {
        if (color1 === color2) {
            color2 = /** @type {string} */ (mixCssColors("#FFFFFF", color1, 0.2));
        }
        return [
            color2,
            mixCssColors("#FFFFFF", color2, 0.9),
            mixCssColors(color1, "#000000", 0.125),
        ];
    }

    test("website configurator: uppercase hex, alpha kept as a fourth byte", () => {
        expect(configuratorPalette("#3AADAA", "#E05D5D")).toEqual([
            "#E05D5D",
            "#FCEFEF",
            "#071615",
        ]);
        expect(configuratorPalette("#FF0000", "#FF0000")).toEqual([
            "#FF3333",
            "#FFEBEB",
            "#200000",
        ]);
        expect(configuratorPalette("#FFFFFF80", "#00000040")).toEqual([
            "#00000040",
            "#E6E6E6EC",
            "#202020EF",
        ]);
        expect(mixCssColors("#714B67", "not-a-color", 0.5)).toBe(false);
    });

    test("html_editor gradient: rgba() with alpha at percent precision", () => {
        expect(mixRgbaColors("#FF000080", "#0000ff", 0.5)).toBe(
            "rgba(128, 0, 128, 0.75)",
        );
        expect(mixRgbaColors("rgba(255, 0, 0, 0.5)", "#00FF00", 0.25)).toBe(
            "rgba(64, 191, 0, 0.88)",
        );
        expect(mixRgbaColors("#123456", "#ABCDEF", 0.37)).toBe(
            "rgba(114, 148, 182, 1)",
        );
        expect(mixRgbaColors("#ffffff", "#00000000", 0.6)).toBe(
            "rgba(153, 153, 153, 0.6)",
        );
        expect(mixRgbaColors("#714B67", "not-a-color", 0.5)).toBe(false);
    });

    test("lighten and darken are mixes toward white and black", () => {
        expect(lightenColor("#714B67", 0.3)).toBe("#9c8195");
        expect(darkenColor("#714B67", 0.3)).toBe("#4f3548");
        expect(lightenColor("#1F77B4", 0.3)).toBe(
            mixHexColors("#FFFFFF", "#1F77B4", 0.3),
        );
        expect(darkenColor("#1F77B4", 1.5)).toBe("#000000");
        expect(lightenColor("tomato", 0.3)).toBe("tomato");
    });

    test("a channel exactly halfway rounds up, whatever the float noise of the weight", () => {
        expect(mixHexColors("#714B67", "#A3A288", 0.15)).toBe("#9c9583");
        expect(mixCssColors("#714B67", "#A3A288", 0.15)).toBe("#9C9583");
        expect(mixRgbaColors("#714B67", "#A3A288", 0.15)).toBe(
            "rgba(156, 149, 131, 1)",
        );
    });
});

describe("one rgb() reader", () => {
    test("space syntax, padded commas and a percentage alpha are colors", () => {
        expect(isCSSColor("rgb(0 0 0)")).toBe(true);
        expect(isCSSColor("rgb( 1 , 2 , 3 )")).toBe(true);
        expect(convertCSSColorToRgba("rgb(0 0 0 / 50%)")).toEqual({
            red: 0,
            green: 0,
            blue: 0,
            opacity: 50,
        });
        expect(isCSSColor("rgba(1, 2, 3, )")).toBe(false);
    });

    test("hex conversion reads what convertCSSColorToRgba reads", () => {
        expect(rgbToHex("rgb(0 0 0 / 50%)")).toBe("#808080");
        expect(rgbaToHex("rgb(0 0 0 / 50%)")).toBe("#00000080");
        expect(rgbToHex("rgb(1.5, 2, 3)")).toBe("#020203");
        expect(rgbToHex("linear")).toBe("#");
        expect(rgbToHex("rgb(255, 0, 0")).toBe("#ff0000");
    });

    test("map opacity multiplies the alpha of an 8-digit hex too", () => {
        const match = /^rgba\(255, 0, 0, ([\d.]+)\)$/.exec(
            withOpacity("#FF000080", 0.5),
        );
        expect(Number(match?.[1])).toBeCloseTo((128 / 255) * 0.5, { margin: 1e-9 });
    });
});
