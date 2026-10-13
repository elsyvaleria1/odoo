/** @odoo-module native */

const URI_SCHEMES = new Map([
    ["lgtin", ["gtin", "class"]],
    ["sgtin", ["gtin", "id"]],
    ["sgtin-96", ["gtin", "tag"]],
    ["sgtin-198", ["gtin", "tag"]],
    ["sscc", ["sscc", "id"]],
    ["sscc-96", ["sscc", "tag"]],
]);
const URI_DATA_FIELDS = { gtin: 3, sscc: 2 };
const URI_KEY_DIGITS = { gtin: 13, sscc: 17 };

const ASCII_DIGITS = /^[0-9]+$/;
const NUMERIC_GROUP = /[{](N*)(D*)[}]/;

const MAX_BARCODE_LENGTH = 256;

const compiledPatterns = new Map();

/**
 * @param {string} pattern
 * @returns {{ regex: RegExp, wholeSize: number | null }}
 */
function compileRulePattern(pattern) {
    let compiled = compiledPatterns.get(pattern);
    if (!compiled) {
        const numericGroup = pattern.match(NUMERIC_GROUP);
        if (numericGroup) {
            const wholeSize = numericGroup[1].length;
            const size = wholeSize + numericGroup[2].length;
            const source =
                pattern.slice(0, numericGroup.index) +
                `(?<value>[0-9]{${size}})` +
                pattern.slice(numericGroup.index + numericGroup[0].length);
            compiled = { regex: new RegExp(`^(?:${source})`, "d"), wholeSize };
        } else {
            compiled = { regex: new RegExp(`^(?:${pattern})`), wholeSize: null };
        }
        compiledPatterns.set(pattern, compiled);
    }
    return compiled;
}

export class BarcodeParser {
    static barcodeNomenclatureFields = ["name", "rule_ids", "upc_ean_conv"];
    static barcodeRuleFields = [
        "name",
        "sequence",
        "type",
        "encoding",
        "pattern",
        "alias",
    ];
    static async fetchNomenclature(orm, id) {
        const [[nomenclature], rules] = await Promise.all([
            orm.read("barcode.nomenclature", [id], this.barcodeNomenclatureFields),
            orm.searchRead(
                "barcode.rule",
                [["barcode_nomenclature_id", "=", id]],
                this.barcodeRuleFields,
            ),
        ]);
        nomenclature.rules = rules;
        return nomenclature;
    }

    constructor() {
        this.setup(...arguments);
    }

    setup({ nomenclature }) {
        this.nomenclature = nomenclature;
    }

    /**
     * @param {String} numericBarcode
     * @returns {number}
     */
    getBarcodeCheckDigit(numericBarcode) {
        let oddsum = 0,
            evensum = 0;
        const code = numericBarcode.split("").reverse();
        code.shift();

        for (let i = 0; i < code.length; i++) {
            if (i % 2 === 0) {
                evensum += parseInt(code[i]);
            } else {
                oddsum += parseInt(code[i]);
            }
        }
        const total = evensum * 3 + oddsum;
        return (10 - (total % 10)) % 10;
    }

    /**
     * @param {String} barcode
     * @param {String} encoding
     * @returns {boolean}
     */
    isBarcodeEncodingValid(barcode, encoding) {
        if (encoding === "any") {
            return true;
        }
        const barcodeSizes = {
            ean8: 8,
            ean13: 13,
            upca: 12,
        };
        return (
            barcode.length === barcodeSizes[encoding] &&
            /^\d+$/.test(barcode) &&
            (encoding !== "ean13" || barcode[0] !== "0") &&
            this.getBarcodeCheckDigit(barcode) === parseInt(barcode[barcode.length - 1])
        );
    }

    /**
     * @param {String} ean
     * @returns {String}
     */
    normalizeEan(ean) {
        ean = ean.substr(0, 13);
        ean = "0".repeat(Math.max(0, 13 - ean.length)) + ean;
        return ean.substr(0, 12) + this.getBarcodeCheckDigit(ean);
    }

    /**
     * @param {String} upc
     * @returns {String}
     */
    normalizeUpc(upc) {
        return this.normalizeEan("0" + upc).substr(1, 12);
    }

    /**
     * @param {String} barcode
     * @param {String} pattern
     * @returns {Object}
     */
    matchPattern(barcode, pattern) {
        const match = {
            value: 0,
            base_code: barcode,
            match: false,
        };
        if (barcode.length > MAX_BARCODE_LENGTH) {
            return match;
        }
        const { regex, wholeSize } = compileRulePattern(pattern);
        const found = regex.exec(barcode);
        if (!found) {
            return match;
        }
        match.match = true;
        const digits = wholeSize === null ? undefined : found.groups.value;
        if (digits === undefined) {
            return match;
        }
        const whole = digits.slice(0, wholeSize) || "0";
        const decimal = digits.slice(wholeSize) || "0";
        match.value = parseFloat(`${whole}.${decimal}`);
        const [start, end] = found.indices.groups.value;
        match.base_code =
            barcode.slice(0, start) + "0".repeat(digits.length) + barcode.slice(end);
        return match;
    }

    /**
     * @param {string} barcode
     * @returns {Object|Object[]}
     */
    parseBarcode(barcode) {
        if (barcode.startsWith("urn:")) {
            return this.parseUri(barcode);
        }
        return this.parseNomenclatureBarcode(barcode);
    }

    parseNomenclatureBarcode(barcode) {
        if (!this.nomenclature) {
            return {
                encoding: "",
                type: "error",
                code: barcode,
                base_code: barcode,
                value: 0,
            };
        }
        const seen = new Set();
        for (;;) {
            const parsedResult = this._matchRules(barcode);
            if (parsedResult.type !== "alias") {
                return parsedResult;
            }
            seen.add(barcode);
            barcode = parsedResult.code;
            if (seen.has(barcode)) {
                parsedResult.type = "error";
                return parsedResult;
            }
        }
    }

    _matchRules(barcode) {
        const parsedResult = {
            encoding: "",
            type: "error",
            code: barcode,
            base_code: barcode,
            value: 0,
        };
        const conv = this.nomenclature.upc_ean_conv;
        const asEan13 =
            ["upc2ean", "always"].includes(conv) &&
            this.isBarcodeEncodingValid(barcode, "upca")
                ? "0" + barcode
                : null;
        const asUpca =
            ["ean2upc", "always"].includes(conv) &&
            barcode[0] === "0" &&
            this.isBarcodeEncodingValid(barcode.slice(1), "upca")
                ? barcode.slice(1)
                : null;

        for (const rule of this.nomenclature.rules) {
            let curBarcode;
            if (rule.encoding === "ean13" && asEan13) {
                curBarcode = asEan13;
            } else if (rule.encoding === "upca" && asUpca) {
                curBarcode = asUpca;
            } else if (this.isBarcodeEncodingValid(barcode, rule.encoding)) {
                curBarcode = barcode;
            } else {
                continue;
            }

            const match = this.matchPattern(curBarcode, rule.pattern);
            if (!match.match) {
                continue;
            }

            if (rule.type === "alias") {
                parsedResult.type = "alias";
                parsedResult.code = rule.alias;
                return parsedResult;
            }

            parsedResult.encoding = rule.encoding;
            parsedResult.type = rule.type;
            parsedResult.value = match.value;
            parsedResult.code = curBarcode;
            if (rule.encoding === "ean13") {
                parsedResult.base_code = this.normalizeEan(match.base_code);
            } else if (rule.encoding === "upca") {
                parsedResult.base_code = this.normalizeUpc(match.base_code);
            } else {
                parsedResult.base_code = match.base_code;
            }
            return parsedResult;
        }
        return parsedResult;
    }

    /**
     * @param {String} barcode
     * @returns {Object[]}
     */
    parseUri(barcode) {
        const parts = barcode.split(":").map((v) => v.trim());
        if (parts.length !== 5) {
            return [];
        }
        const [, namespace, uriType, identifier] = parts;
        let data = parts[4].split(".");

        const scheme = URI_SCHEMES.get(identifier);
        if (!scheme || namespace !== "epc" || uriType !== scheme[1]) {
            return [];
        }
        const [key] = scheme;
        const filtered = uriType === "tag";
        if (data.length !== URI_DATA_FIELDS[key] + (filtered ? 1 : 0)) {
            return [];
        }
        if (filtered) {
            data = data.slice(1);
        }
        const [companyPrefix, reference] = data;
        if (
            !ASCII_DIGITS.test(companyPrefix) ||
            !ASCII_DIGITS.test(reference) ||
            companyPrefix.length + reference.length !== URI_KEY_DIGITS[key]
        ) {
            return [];
        }

        if (key === "sscc") {
            return this.convertUriSsccDataIntoPackage(barcode, data);
        }
        return this.convertUriGtinDataIntoTrackingNumber(barcode, data);
    }

    convertUriGtinDataIntoTrackingNumber(base_code, data) {
        const [gs1CompanyPrefix, itemRefAndIndicator, trackingNumber] = data;
        const indicator = itemRefAndIndicator[0];
        const itemRef = itemRefAndIndicator.slice(1);
        let productBarcode = indicator + gs1CompanyPrefix + itemRef;
        productBarcode += this.getBarcodeCheckDigit(productBarcode + "0");
        return [
            {
                base_code,
                code: productBarcode,
                encoding: "",
                type: "product",
                value: productBarcode,
            },
            {
                base_code,
                code: trackingNumber,
                encoding: "",
                type: "lot",
                value: trackingNumber,
            },
        ];
    }

    convertUriSsccDataIntoPackage(base_code, data) {
        const [gs1CompanyPrefix, serialReference] = data;
        const extension = serialReference[0];
        const serialRef = serialReference.slice(1);
        let sscc = extension + gs1CompanyPrefix + serialRef;
        sscc += this.getBarcodeCheckDigit(sscc + "0");
        return [
            {
                base_code,
                code: sscc,
                encoding: "",
                type: "package",
                value: sscc,
            },
        ];
    }
}
