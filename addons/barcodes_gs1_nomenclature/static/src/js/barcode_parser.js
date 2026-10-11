/** @odoo-module native */
import { BarcodeParser } from "@barcodes/js/barcode_parser";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
export class GS1BarcodeError extends Error {}

export const FNC1_CHAR = String.fromCharCode(29);
const SYMBOLOGY_IDENTIFIERS = ["]C1", "]e0", "]d2", "]Q3", "]J1"];
const ASCII_DIGITS = /^[0-9]+$/;

const elementRegexes = new Map();

function gs1ElementRegex(pattern) {
    let regex = elementRegexes.get(pattern);
    if (!regex) {
        regex = new RegExp(`^${pattern}(?:${FNC1_CHAR}+)?`);
        elementRegexes.set(pattern, regex);
    }
    return regex;
}

patch(BarcodeParser, {
    barcodeNomenclatureFields: [
        ...BarcodeParser.barcodeNomenclatureFields,
        "is_gs1_nomenclature",
        "gs1_separator_fnc1",
    ],
    barcodeRuleFields: [
        ...BarcodeParser.barcodeRuleFields,
        "gs1_content_type",
        "gs1_decimal_usage",
        "associated_uom_id",
    ],
});

patch(BarcodeParser.prototype, {
    setup() {
        super.setup(...arguments);
        const nomenclatureSeparator =
            this.nomenclature && this.nomenclature.gs1_separator_fnc1;
        this.gs1SeparatorRegex = new RegExp(nomenclatureSeparator || ".^", "g");
    },

    /**
     * Convert YYMMDD GS1 date into a Date object
     *
     * @param {string} gs1Date YYMMDD string date, length must be 6
     * @returns {Date|null} null when the digits name no calendar day
     */
    gs1DateToDate(gs1Date) {
        const now = new Date();
        const twoDigitYear = parseInt(gs1Date.slice(0, 2), 10);
        const month = parseInt(gs1Date.slice(2, 4), 10);
        const day = parseInt(gs1Date.slice(4, 6), 10);
        const substractYear = twoDigitYear - (now.getFullYear() % 100);
        let century = Math.floor(now.getFullYear() / 100);
        if (51 <= substractYear && substractYear <= 99) {
            century--;
        } else if (-99 <= substractYear && substractYear <= -50) {
            century++;
        }
        const year = century * 100 + twoDigitYear;
        const lastDay = new Date(year, month, 0).getDate();
        if (month < 1 || month > 12 || day > lastDay) {
            return null;
        }
        return new Date(year, month - 1, day || lastDay);
    },

    /**
     * Read a matched GS1 element as its rule's content type. Mirrors
     * `barcode.nomenclature.parse_gs1_rule_pattern`: content the type cannot
     * hold is not this rule.
     *
     * @param {Array} match Result of a regex match with at most 2 groups (ai and value)
     * @param {Object} rule Matched Barcode Rule
     * @returns {Object|null}
     */
    parseGs1RulePattern(match, rule) {
        const [, ai, raw] = match;
        const value = this._gs1ElementValue(rule, ai, raw);
        if (value === null) {
            return null;
        }
        return {
            rule: Object.assign({}, rule),
            ai,
            string_value: raw,
            code: raw,
            base_code: raw,
            type: rule.type,
            value,
        };
    },

    _gs1ElementValue(rule, ai, raw) {
        const contentType = rule.gs1_content_type;
        if (contentType === "alpha" || !contentType) {
            return raw;
        }
        if (!ASCII_DIGITS.test(raw)) {
            return null;
        }
        if (contentType === "measure") {
            let decimals = 0;
            if (rule.gs1_decimal_usage) {
                if (!ASCII_DIGITS.test(ai.slice(-1))) {
                    return null;
                }
                decimals = parseInt(ai.slice(-1), 10);
            }
            if (decimals > raw.length) {
                return null;
            }
            if (!decimals) {
                return parseInt(raw, 10);
            }
            const whole = raw.slice(0, raw.length - decimals) || "0";
            return parseFloat(`${whole}.${raw.slice(raw.length - decimals)}`);
        }
        if (contentType === "identifier") {
            const checkDigit = this.getBarcodeCheckDigit(raw.padStart(18, "0"));
            return raw.endsWith(String(checkDigit)) ? raw : null;
        }
        if (raw.length !== 6) {
            return null;
        }
        return this.gs1DateToDate(raw);
    },

    /**
     * Decompose a GS1 element string into its elements, in order. Mirrors
     * `barcode.nomenclature.gs1_decompose_extended`: each element is matched
     * from the first rule again, by sequence.
     *
     * @param {string} barcode
     * @returns {Array} Array of object
     */
    gs1DecomposeExtended(barcode) {
        const rules = this.nomenclature.rules.filter(
            (rule) => rule.encoding === "gs1-128",
        );
        const regexes = rules.map((rule) => [rule, gs1ElementRegex(rule.pattern)]);
        barcode = this._convertGs1Separators(barcode);
        const identifier = SYMBOLOGY_IDENTIFIERS.find((id) => barcode.startsWith(id));
        if (identifier) {
            barcode = barcode.slice(identifier.length);
        }
        barcode = this.cleanBarcode(barcode);

        const results = [];
        while (barcode.length > 0) {
            const [element, consumed] = this._nextGs1Element(barcode, regexes);
            if (!consumed) {
                throw new GS1BarcodeError(
                    _t("This barcode can't be partially or fully parsed."),
                );
            }
            results.push(element);
            barcode = barcode.slice(consumed);
        }
        return results;
    },

    _nextGs1Element(barcode, regexes) {
        for (const [rule, regex] of regexes) {
            const match = barcode.match(regex);
            if (match && match.length >= 3) {
                const element = this.parseGs1RulePattern(match, rule);
                if (element) {
                    return [element, match[0].length];
                }
            }
        }
        return [null, 0];
    },

    /**
     * @override
     * @returns {Object|Array|null} If nomenclature is GS1, returns an array or null
     */
    parseNomenclatureBarcode(barcode) {
        if (this.nomenclature && this.nomenclature.is_gs1_nomenclature) {
            return this.gs1DecomposeExtended(barcode);
        }
        return super.parseNomenclatureBarcode(...arguments);
    },

    /**
     * Makes all needed operations to clean and prepare the barcode.
     * @param {string} barcode
     * @returns {string}
     */
    cleanBarcode(barcode) {
        let start = 0;
        while (barcode[start] === FNC1_CHAR) {
            start++;
        }
        return barcode.slice(start);
    },

    /**
     * The FNC1 is the default GS1 separator character, but through the field `gs1_separator_fnc1`,
     * the user has the possibility to define one or multiple characters to use as separator as
     * a regex. This method replaces all of the matches in the given barcode by the FNC1.
     *
     * @param {string} barcode
     * @returns {string}
     */
    _convertGs1Separators: function (barcode) {
        barcode = barcode.replace(this.gs1SeparatorRegex, FNC1_CHAR);
        return barcode;
    },
});
