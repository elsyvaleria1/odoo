// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";
import { clamp } from "@web/core/utils/format/numbers";

const log = makeLogger("web.colors");

/**
 * @typedef {{ red: number, green: number, blue: number, opacity: number }} RgbaColor
 * @typedef {{ red: number, green: number, blue: number, alpha: number }} RgbFunction
 */

/**
 * @param {string} gradient
 * @param {number} opacity
 * @returns {string}
 */
export function applyOpacityToGradient(gradient, opacity = 100) {
    if (opacity === 100) {
        return gradient;
    }
    return gradient.replace(/rgb\(([^)]+)\)/g, `rgba($1, ${opacity / 100.0})`);
}
/**
 * @param {number} r
 * @param {number} g
 * @param {number} b
 * @returns {Object|false}
 */
export function convertRgbToHsl(r, g, b) {
    if (
        typeof r !== "number" ||
        Number.isNaN(r) ||
        r < 0 ||
        r > 255 ||
        typeof g !== "number" ||
        Number.isNaN(g) ||
        g < 0 ||
        g > 255 ||
        typeof b !== "number" ||
        Number.isNaN(b) ||
        b < 0 ||
        b > 255
    ) {
        return false;
    }

    const red = r / 255;
    const green = g / 255;
    const blue = b / 255;
    const maxColor = Math.max(red, green, blue);
    const minColor = Math.min(red, green, blue);
    const delta = maxColor - minColor;
    let hue = 0;
    let saturation = 0;
    const lightness = (maxColor + minColor) / 2;
    if (delta) {
        if (maxColor === red) {
            hue = (green - blue) / delta;
        }
        if (maxColor === green) {
            hue = 2 + (blue - red) / delta;
        }
        if (maxColor === blue) {
            hue = 4 + (red - green) / delta;
        }
        saturation = delta / (1 - Math.abs(2 * lightness - 1));
    }
    hue = 60 * hue;
    return {
        hue: hue < 0 ? hue + 360 : hue,
        saturation: saturation * 100,
        lightness: lightness * 100,
    };
}
/**
 * @param {number} h
 * @param {number} s
 * @param {number} l
 * @returns {Object|false}
 */
export function convertHslToRgb(h, s, l) {
    if (
        typeof h !== "number" ||
        Number.isNaN(h) ||
        h < 0 ||
        h > 360 ||
        typeof s !== "number" ||
        Number.isNaN(s) ||
        s < 0 ||
        s > 100 ||
        typeof l !== "number" ||
        Number.isNaN(l) ||
        l < 0 ||
        l > 100
    ) {
        return false;
    }

    const huePrime = h / 60;
    const saturation = s / 100;
    const lightness = l / 100;
    let chroma = saturation * (1 - Math.abs(2 * lightness - 1));
    let secondComponent = chroma * (1 - Math.abs((huePrime % 2) - 1));
    let lightnessAdjustment = lightness - chroma / 2;
    const precision = 255;
    chroma = Math.round((chroma + lightnessAdjustment) * precision);
    secondComponent = Math.round((secondComponent + lightnessAdjustment) * precision);
    lightnessAdjustment = Math.round(lightnessAdjustment * precision);
    if (huePrime >= 0 && huePrime < 1) {
        return {
            red: chroma,
            green: secondComponent,
            blue: lightnessAdjustment,
        };
    }
    if (huePrime >= 1 && huePrime < 2) {
        return {
            red: secondComponent,
            green: chroma,
            blue: lightnessAdjustment,
        };
    }
    if (huePrime >= 2 && huePrime < 3) {
        return {
            red: lightnessAdjustment,
            green: chroma,
            blue: secondComponent,
        };
    }
    if (huePrime >= 3 && huePrime < 4) {
        return {
            red: lightnessAdjustment,
            green: secondComponent,
            blue: chroma,
        };
    }
    if (huePrime >= 4 && huePrime < 5) {
        return {
            red: secondComponent,
            green: lightnessAdjustment,
            blue: chroma,
        };
    }
    if (huePrime >= 5 && huePrime <= 6) {
        return {
            red: chroma,
            green: lightnessAdjustment,
            blue: secondComponent,
        };
    }
    return false;
}
/**
 * @param {number} r
 * @param {number} g
 * @param {number} b
 * @param {number} [a]
 * @returns {string | false}
 */
export function convertRgbaToCSSColor(r, g, b, a) {
    const channels = [r, g, b].map((channel) =>
        typeof channel === "number" ? Math.round(channel) : Number.NaN,
    );
    if (channels.some((channel) => !(channel >= 0 && channel <= 255))) {
        return false;
    }
    const [rr, gg, bb] = channels.map((channel) =>
        channel.toString(16).padStart(2, "0"),
    );
    if (
        typeof a !== "number" ||
        Number.isNaN(a) ||
        a < 0 ||
        a > 100 ||
        Math.abs(a - 100) < Number.EPSILON
    ) {
        return `#${rr}${gg}${bb}`.toUpperCase();
    }
    const aa = opacityToHex(a);
    return `#${rr}${gg}${bb}${aa}`.toUpperCase();
}

/**
 * @param {number} opacity Percentage from 0 to 100.
 * @returns {string}
 */
export function opacityToHex(opacity) {
    return Math.round((opacity / 100) * 255)
        .toString(16)
        .padStart(2, "0");
}
const RGB_FUNCTION_REGEX =
    /^rgba?\(\s*(\d*\.?\d+)\s*(?:,\s*|\s+)(\d*\.?\d+)\s*(?:,\s*|\s+)(\d*\.?\d+)\s*(?:[,/]\s*(\d*\.?\d+)(%?)\s*)?\)$/;

/**
 * The one reader of `rgb()` / `rgba()`, comma or space syntax, alpha as a
 * fraction or a percentage. Channels and alpha are returned unrounded.
 *
 * @param {string} value
 * @returns {RgbFunction | null}
 */
function parseRgbFunction(value) {
    const match = RGB_FUNCTION_REGEX.exec(value);
    if (!match) {
        return null;
    }
    const [, red, green, blue, alpha, percent] = match;
    const fraction = alpha === undefined ? 1 : Number(alpha);
    return {
        red: Number(red),
        green: Number(green),
        blue: Number(blue),
        alpha: percent ? fraction / 100 : fraction,
    };
}

/**
 * A color literal -- hex, `rgb()` or `rgba()` -- read by the grammar the
 * server reads the image shape colors with (`parse_css_rgba` in html_editor):
 * html_editor's color conformance vectors hold the two to one result.
 *
 * @param {string} cssColor
 * @returns {RgbaColor | false}
 */
export function parseCSSColor(cssColor = "") {
    const rgb = parseRgbFunction(cssColor);
    if (rgb) {
        return {
            red: Math.round(rgb.red),
            green: Math.round(rgb.green),
            blue: Math.round(rgb.blue),
            opacity: Math.round(rgb.alpha * 100),
        };
    }

    if (/^#([0-9a-f]{3})$/i.test(cssColor)) {
        return {
            red: Number.parseInt(cssColor[1] + cssColor[1], 16),
            green: Number.parseInt(cssColor[2] + cssColor[2], 16),
            blue: Number.parseInt(cssColor[3] + cssColor[3], 16),
            opacity: 100,
        };
    }

    if (/^#([0-9A-F]{6}|[0-9A-F]{8})$/i.test(cssColor)) {
        return {
            red: Number.parseInt(cssColor.slice(1, 3), 16),
            green: Number.parseInt(cssColor.slice(3, 5), 16),
            blue: Number.parseInt(cssColor.slice(5, 7), 16),
            opacity:
                (cssColor.length === 9
                    ? Number.parseInt(cssColor.slice(7, 9), 16) / 255
                    : 1) * 100,
        };
    }

    return false;
}

/**
 * Any color `parseCSSColor` reads, and the `color()` a browser computes (a
 * `color-mix()` resolves to one), read through a canvas.
 *
 * @param {string} cssColor
 * @returns {RgbaColor | false}
 */
export function convertCSSColorToRgba(cssColor = "") {
    const rgba = parseCSSColor(cssColor);
    if (rgba) {
        return rgba;
    }
    if (/color\(.+\)/.test(cssColor)) {
        const canvasEl = document.createElement("canvas");
        canvasEl.height = 1;
        canvasEl.width = 1;
        const ctx = canvasEl.getContext("2d");
        if (!ctx) {
            return false;
        }
        ctx.fillStyle = cssColor;
        ctx.fillRect(0, 0, 1, 1);
        const data = ctx.getImageData(0, 0, 1, 1).data;
        return {
            red: data[0],
            green: data[1],
            blue: data[2],
            opacity: data[3] / 2.55,
        };
    }
    return false;
}
/**
 * @param {string} cssColor
 * @returns {string}
 */
export function normalizeCSSColor(cssColor) {
    const rgba = convertCSSColorToRgba(cssColor);
    if (!rgba) {
        return cssColor;
    }
    return /** @type {string} */ (
        convertRgbaToCSSColor(rgba.red, rgba.green, rgba.blue, rgba.opacity)
    );
}
/**
 * @param {string} cssColor
 * @returns {boolean}
 */
export function isCSSColor(cssColor) {
    return convertCSSColorToRgba(cssColor) !== false;
}
/**
 * Mix as a normalized CSS hex (`#RRGGBB`, or `#RRGGBBAA` when translucent).
 *
 * @param {string} cssColor1
 * @param {string} cssColor2
 * @param {number} weight Weight belonging to the first color.
 * @returns {string | false}
 */
export function mixCssColors(cssColor1, cssColor2, weight) {
    const mix = mixColors(cssColor1, cssColor2, weight);
    return mix && convertRgbaToCSSColor(mix.red, mix.green, mix.blue, mix.opacity);
}

/**
 * @param {string} [value]
 * @returns {boolean}
 */
export function isColorGradient(value) {
    return Boolean(value?.includes("-gradient("));
}

/**
 * @param {string} gradient
 * @returns {string}
 */
export function standardizeGradient(gradient) {
    if (isColorGradient(gradient)) {
        const el = document.createElement("div");
        el.style.setProperty("background-image", gradient);
        gradient = el.style.getPropertyValue("background-image");
    }
    return gradient;
}

/**
 * @param {number[]} channels
 * @returns {string}
 */
function toLowerHex(channels) {
    return (
        "#" +
        channels
            .map((channel) =>
                clamp(Math.round(channel), 0, 255).toString(16).padStart(2, "0"),
            )
            .join("")
    );
}

/**
 * `#rrggbb` for an opaque `rgb()`; a translucent one is blended onto the
 * background of `node` (white by default). "#" when `rgb` is not a color.
 *
 * @param {string} rgb
 * @param {HTMLElement | null} [node]
 * @returns {string}
 */
export function rgbToHex(rgb = "", node = null) {
    if (rgb.startsWith("#")) {
        return rgb;
    }
    const parsed = parseRgbFunction(rgb);
    if (!parsed) {
        log.logic("rgbToHex: not an rgb() color", () => ({ rgb }));
        return "#";
    }
    if (parsed.alpha < 1) {
        return blendColors(rgb, node);
    }
    return toLowerHex([parsed.red, parsed.green, parsed.blue]);
}

/**
 * `#RRGGBB[AA]`, uppercase like `normalizeCSSColor`, for any color
 * `convertCSSColorToRgba` reads; an `rgb()` alpha is kept unrounded and its
 * channels clamped as CSS does. "#" when `color` is not a color.
 *
 * @param {string} color
 * @returns {string}
 */
export function rgbaToHex(color = "") {
    const rgb = parseRgbFunction(color);
    const rgba = rgb
        ? {
              red: clamp(rgb.red, 0, 255),
              green: clamp(rgb.green, 0, 255),
              blue: clamp(rgb.blue, 0, 255),
              opacity: rgb.alpha * 100,
          }
        : convertCSSColorToRgba(color);
    const hex =
        rgba && convertRgbaToCSSColor(rgba.red, rgba.green, rgba.blue, rgba.opacity);
    log.logic("rgbaToHex", () => ({ color, rgbFunction: Boolean(rgb), hex }));
    return hex || "#";
}

/**
 * @param {HTMLElement | null | undefined} node
 * @returns {[number, number, number]}
 */
function getBackgroundChannels(node) {
    if (!node) {
        return [255, 255, 255];
    }
    let bgColor = getComputedStyle(node).backgroundColor;
    if (bgColor.startsWith("rgba")) {
        bgColor = blendColors(bgColor, node.parentElement);
    }
    const bg = convertCSSColorToRgba(bgColor);
    log.logic("blendColors: background", () => ({ bgColor, parsed: Boolean(bg) }));
    return bg ? [bg.red, bg.green, bg.blue] : [255, 255, 255];
}

/**
 * Flatten an `rgb()` / `rgba()` onto the background of `node` (white by
 * default) as `#rrggbb`. Other inputs go through `rgbToHex`.
 *
 * @param {string} color
 * @param {HTMLElement|null} [node]
 * @returns {string}
 */
export function blendColors(color, node) {
    const parsed = parseRgbFunction(color);
    if (!parsed) {
        log.logic("blendColors: not an rgb() color", () => ({ color }));
        return rgbToHex(color);
    }
    const { alpha } = parsed;
    const bg = alpha < 1 ? getBackgroundChannels(node) : [0, 0, 0];
    return toLowerHex(
        [parsed.red, parsed.green, parsed.blue].map(
            (channel, index) => alpha * channel + (1 - alpha) * bg[index],
        ),
    );
}

const BARE_HEX_REGEX = /^(?:[a-f\d]{3}|[a-f\d]{6})$/i;

/**
 * @param {string} color
 * @returns {RgbaColor | false}
 */
function toRgba(color = "") {
    color = color.trim();
    return convertCSSColorToRgba(BARE_HEX_REGEX.test(color) ? `#${color}` : color);
}

/**
 * Weighted sRGB brightness, without gamma correction (not WCAG luminance).
 * @param {string} color
 * @returns {number}
 */
export function getColorBrightness(color) {
    const rgb = toRgba(color);
    return rgb ? (0.299 * rgb.red + 0.587 * rgb.green + 0.114 * rgb.blue) / 255 : 0;
}

/**
 * @param {string} color
 * @returns {string}
 */
export function colorToRgb(color) {
    const rgb = toRgba(color);
    return rgb ? `${rgb.red}, ${rgb.green}, ${rgb.blue}` : "0, 0, 0";
}

/**
 * Format RGB channels and an optional fractional alpha as a CSS rgb() value.
 * @param {number[]} channels
 * @returns {string}
 */
export function formatRgb(channels) {
    return `rgb(${channels.join(",")})`;
}

/** @returns {string} */
export function randomColor() {
    return `#${Math.floor(Math.random() * 0x1000000)
        .toString(16)
        .padStart(6, "0")}`.toUpperCase();
}

/**
 * @param {number} from
 * @param {number} to
 * @param {number} weight
 * @returns {number}
 */
function lerp(from, to, weight) {
    return from + (to - from) * weight;
}

/**
 * The one color mixer; the exported `mix*Colors` only format its result.
 * Channels are rounded, opacity is left exact for the formatter.
 *
 * @param {string} color1
 * @param {string} color2
 * @param {number} weight Weight belonging to the first color.
 * @returns {RgbaColor | false}
 */
function mixColors(color1, color2, weight) {
    const rgba1 = toRgba(color1);
    const rgba2 = toRgba(color2);
    if (!rgba1 || !rgba2) {
        log.logic("mixColors: unparsable color", () => ({
            color1,
            color2,
            parsed1: Boolean(rgba1),
            parsed2: Boolean(rgba2),
        }));
        return false;
    }
    return {
        red: Math.round(lerp(rgba2.red, rgba1.red, weight)),
        green: Math.round(lerp(rgba2.green, rgba1.green, weight)),
        blue: Math.round(lerp(rgba2.blue, rgba1.blue, weight)),
        opacity: lerp(rgba2.opacity, rgba1.opacity, weight),
    };
}

/**
 * Mix as an opaque `#rrggbb`, alpha dropped; `color2` when either is not a color.
 *
 * @param {string} color1
 * @param {string} color2
 * @param {number} weight Weight belonging to the first color.
 * @returns {string}
 */
export function mixHexColors(color1, color2, weight) {
    const mix = mixColors(color1, color2, weight);
    return mix ? toLowerHex([mix.red, mix.green, mix.blue]) : color2;
}

/**
 * Mix as `rgba()`, alpha rounded to the gradient editor's percentage precision.
 *
 * @param {string} color1
 * @param {string} color2
 * @param {number} weight Weight belonging to the first color.
 * @returns {string | false}
 */
export function mixRgbaColors(color1, color2, weight) {
    const mix = mixColors(color1, color2, weight);
    return (
        mix &&
        `rgba(${mix.red}, ${mix.green}, ${mix.blue}, ${Math.round(mix.opacity) / 100})`
    );
}

/**
 * @param {string} color
 * @param {number} factor
 * @returns {string}
 */
export function lightenColor(color, factor) {
    return mixHexColors("#FFFFFF", color, clamp(factor, 0, 1));
}

/**
 * @param {string} color
 * @param {number} factor
 * @returns {string}
 */
export function darkenColor(color, factor) {
    return mixHexColors("#000000", color, clamp(factor, 0, 1));
}

/**
 * One answer for "this colour, at this opacity", for the three renderers that
 * used to carry their own. Accepts hex, rgb() and rgba(), multiplying any
 * alpha they carry; anything else is returned unchanged.
 *
 * @param {string} color
 * @param {number} [opacity]
 * @returns {string}
 */
export function withOpacity(color, opacity) {
    if (!color || opacity === undefined || opacity === null || opacity >= 1) {
        return color;
    }
    const rgb = parseRgbFunction(color);
    if (rgb) {
        return `rgba(${rgb.red}, ${rgb.green}, ${rgb.blue}, ${rgb.alpha * opacity})`;
    }
    const hex = color.startsWith("#") && convertCSSColorToRgba(color);
    if (hex) {
        const alpha = hex.opacity === 100 ? opacity : (hex.opacity / 100) * opacity;
        return `rgba(${hex.red}, ${hex.green}, ${hex.blue}, ${alpha})`;
    }
    log.logic("withOpacity: left unchanged", () => ({ color, opacity }));
    return color;
}
