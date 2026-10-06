/** @odoo-module native */
/**
 * Golden vectors for GS1 decomposition, the one source of truth for both
 * runtimes: barcodes_gs1_nomenclature/models/barcode_nomenclature.py and
 * static/src/js/barcode_parser.js decompose the same barcodes, and nothing
 * held them to the same answer.
 *
 * Read by:
 *   JS     -> static/tests/gs1_conformance.test.js
 *   Python -> tests/test_gs1_conformance.py, which slices the raw template
 *             literal below and json.loads it.
 *
 * `expected` is the list of decomposed parts in order, or null when the
 * barcode does not decompose. A date is its ISO day. Dates stay within fifty
 * years of today, where GS1's century rule reads them as written.
 */

export const GS1_VECTORS = JSON.parse(String.raw`
{
    "rule_sets": {
        "default": [
            {
                "sequence": 101,
                "pattern": "(01)(\\d{14})",
                "type": "product",
                "gs1_content_type": "identifier"
            },
            {
                "sequence": 125,
                "pattern": "(10)([!\"%-/0-9:-?A-Z_a-z]{0,20})",
                "type": "lot",
                "gs1_content_type": "alpha"
            },
            {
                "sequence": 139,
                "pattern": "(17)(\\d{6})",
                "type": "expiration_date",
                "gs1_content_type": "date"
            },
            {
                "sequence": 310,
                "pattern": "(310[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 370,
                "pattern": "(37)(\\d{0,8})",
                "type": "quantity",
                "gs1_content_type": "measure"
            }
        ],
        "order": [
            {
                "sequence": 10,
                "pattern": "(21)(\\d{3})",
                "type": "lot",
                "gs1_content_type": "alpha"
            },
            {
                "sequence": 20,
                "pattern": "(10)([A-Z]{2})",
                "type": "lot",
                "gs1_content_type": "alpha"
            },
            {
                "sequence": 30,
                "pattern": "(21)(\\d{2})",
                "type": "package",
                "gs1_content_type": "alpha"
            }
        ],
        "loose_measure": [
            {
                "sequence": 10,
                "pattern": "(37)(\\w{0,8})",
                "type": "quantity",
                "gs1_content_type": "measure"
            }
        ],
        "shipped": [
            {
                "sequence": 100,
                "pattern": "(00)(\\d{18})",
                "type": "package",
                "gs1_content_type": "identifier"
            },
            {
                "sequence": 101,
                "pattern": "(01)(\\d{14})",
                "type": "product",
                "gs1_content_type": "identifier"
            },
            {
                "sequence": 102,
                "pattern": "(02)(\\d{14})",
                "type": "product",
                "gs1_content_type": "identifier"
            },
            {
                "sequence": 110,
                "pattern": "(410)(\\d{13})",
                "type": "location_dest",
                "gs1_content_type": "identifier"
            },
            {
                "sequence": 113,
                "pattern": "(413)(\\d{13})",
                "type": "location_dest",
                "gs1_content_type": "identifier"
            },
            {
                "sequence": 114,
                "pattern": "(414)(\\d{13})",
                "type": "location",
                "gs1_content_type": "identifier"
            },
            {
                "sequence": 125,
                "pattern": "(10)([!\"%-/0-9:-?A-Z_a-z]{0,20})",
                "type": "lot",
                "gs1_content_type": "alpha"
            },
            {
                "sequence": 126,
                "pattern": "(21)([!\"%-/0-9:-?A-Z_a-z]{0,20})",
                "type": "lot",
                "gs1_content_type": "alpha"
            },
            {
                "sequence": 137,
                "pattern": "(13)(\\d{6})",
                "type": "pack_date",
                "gs1_content_type": "date"
            },
            {
                "sequence": 138,
                "pattern": "(15)(\\d{6})",
                "type": "use_date",
                "gs1_content_type": "date"
            },
            {
                "sequence": 139,
                "pattern": "(17)(\\d{6})",
                "type": "expiration_date",
                "gs1_content_type": "date"
            },
            {
                "sequence": 300,
                "pattern": "(30)(\\d{0,8})",
                "type": "quantity",
                "gs1_content_type": "measure"
            },
            {
                "sequence": 305,
                "pattern": "(37)(\\d{0,8})",
                "type": "quantity",
                "gs1_content_type": "measure"
            },
            {
                "sequence": 310,
                "pattern": "(310[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 311,
                "pattern": "(311[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 314,
                "pattern": "(314[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 315,
                "pattern": "(315[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 316,
                "pattern": "(316[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 320,
                "pattern": "(320[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 321,
                "pattern": "(321[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 322,
                "pattern": "(322[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 323,
                "pattern": "(323[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 351,
                "pattern": "(351[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 357,
                "pattern": "(357[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 360,
                "pattern": "(360[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 361,
                "pattern": "(361[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 364,
                "pattern": "(364[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 365,
                "pattern": "(365[0-5])(\\d{6})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            },
            {
                "sequence": 500,
                "pattern": "(91)([!\"%-/0-9:-?A-Z_a-z]{0,90})",
                "type": "package_type",
                "gs1_content_type": "alpha"
            }
        ],
        "decimals": [
            {
                "sequence": 10,
                "pattern": "(300)(\\d{5,8})",
                "type": "quantity",
                "gs1_content_type": "measure"
            },
            {
                "sequence": 20,
                "pattern": "(304)(\\d{5,8})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            }
        ],
        "no_decimal_ai": [
            {
                "sequence": 10,
                "pattern": "()(\\d{0,4})",
                "type": "quantity",
                "gs1_content_type": "measure",
                "gs1_decimal_usage": true
            }
        ]
    },
    "cases": [
        {
            "_why": "a GTIN then a trailing variable-length lot",
            "rules": "default",
            "barcode": "010000000000123610LOT1",
            "expected": [
                {
                    "type": "product",
                    "ai": "01",
                    "value": "00000000001236"
                },
                {
                    "type": "lot",
                    "ai": "10",
                    "value": "LOT1"
                }
            ]
        },
        {
            "_why": "a separator ends a variable-length field",
            "rules": "default",
            "separator": "#",
            "barcode": "10LOT1#17301231",
            "expected": [
                {
                    "type": "lot",
                    "ai": "10",
                    "value": "LOT1"
                },
                {
                    "type": "expiration_date",
                    "ai": "17",
                    "value": "2030-12-31"
                }
            ]
        },
        {
            "_why": "a run of separators is one separator",
            "rules": "default",
            "separator": "#",
            "barcode": "10LOT1##17301231",
            "expected": [
                {
                    "type": "lot",
                    "ai": "10",
                    "value": "LOT1"
                },
                {
                    "type": "expiration_date",
                    "ai": "17",
                    "value": "2030-12-31"
                }
            ]
        },
        {
            "_why": "the FNC1 character separates without configuration",
            "rules": "default",
            "barcode": "10LOT1\u001d17301231",
            "expected": [
                {
                    "type": "lot",
                    "ai": "10",
                    "value": "LOT1"
                },
                {
                    "type": "expiration_date",
                    "ai": "17",
                    "value": "2030-12-31"
                }
            ]
        },
        {
            "_why": "day 00 is the last day of the month",
            "rules": "default",
            "barcode": "17300200",
            "expected": [
                {
                    "type": "expiration_date",
                    "ai": "17",
                    "value": "2030-02-28"
                }
            ]
        },
        {
            "_why": "month 13 is no date: not this rule, never a rolled-over one",
            "rules": "default",
            "barcode": "17301301",
            "expected": null
        },
        {
            "_why": "the 31st of February is no date either",
            "rules": "default",
            "barcode": "17300231",
            "expected": null
        },
        {
            "_why": "the AI's last digit places the decimal point",
            "rules": "default",
            "barcode": "3102000125",
            "expected": [
                {
                    "type": "quantity",
                    "ai": "3102",
                    "value": 1.25
                }
            ]
        },
        {
            "_why": "a measure without decimals is an integer",
            "rules": "default",
            "barcode": "3712",
            "expected": [
                {
                    "type": "quantity",
                    "ai": "37",
                    "value": 12
                }
            ]
        },
        {
            "_why": "a wrong check digit is not this rule",
            "rules": "default",
            "barcode": "0100000000001237",
            "expected": null
        },
        {
            "_why": "a scanner's symbology identifier is not data",
            "rules": "default",
            "barcode": "]C10100000000001236",
            "expected": [
                {
                    "type": "product",
                    "ai": "01",
                    "value": "00000000001236"
                }
            ]
        },
        {
            "_why": "a leading FNC1 is not data",
            "rules": "default",
            "barcode": "\u001d0100000000001236",
            "expected": [
                {
                    "type": "product",
                    "ai": "01",
                    "value": "00000000001236"
                }
            ]
        },
        {
            "_why": "each segment is matched from the first rule again",
            "rules": "order",
            "barcode": "10AB21123",
            "expected": [
                {
                    "type": "lot",
                    "ai": "10",
                    "value": "AB"
                },
                {
                    "type": "lot",
                    "ai": "21",
                    "value": "123"
                }
            ]
        },
        {
            "_why": "a measure that is not digits is not this rule",
            "rules": "loose_measure",
            "barcode": "3712a",
            "expected": null
        },
        {
            "_why": "what no rule reads does not decompose",
            "rules": "default",
            "barcode": "99ABC",
            "expected": null
        },
        {
            "_why": "the shipped rules read a GTIN, a lot, a weight and a date around FNC1s",
            "rules": "shipped",
            "barcode": "\u001d01940190976854571033650100138\u001d310200200415131018",
            "expected": [
                {
                    "type": "product",
                    "ai": "01",
                    "value": "94019097685457"
                },
                {
                    "type": "lot",
                    "ai": "10",
                    "value": "33650100138"
                },
                {
                    "type": "quantity",
                    "ai": "3102",
                    "value": 20.04
                },
                {
                    "type": "use_date",
                    "ai": "15",
                    "value": "2013-10-18"
                }
            ]
        },
        {
            "_why": "a pack date then a count",
            "rules": "shipped",
            "barcode": "0194019097685457131701193017",
            "expected": [
                {
                    "type": "product",
                    "ai": "01",
                    "value": "94019097685457"
                },
                {
                    "type": "pack_date",
                    "ai": "13",
                    "value": "2017-01-19"
                },
                {
                    "type": "quantity",
                    "ai": "30",
                    "value": 17
                }
            ]
        },
        {
            "_why": "a count padded, prefixed with FNC1 or ended by one reads the same",
            "rules": "shipped",
            "barcode": "0194019097685457300000001713170119",
            "expected": [
                {
                    "type": "product",
                    "ai": "01",
                    "value": "94019097685457"
                },
                {
                    "type": "quantity",
                    "ai": "30",
                    "value": 17
                },
                {
                    "type": "pack_date",
                    "ai": "13",
                    "value": "2017-01-19"
                }
            ]
        },
        {
            "_why": "a count padded, prefixed with FNC1 or ended by one reads the same",
            "rules": "shipped",
            "barcode": "\u001d0194019097685457300000001713170119",
            "expected": [
                {
                    "type": "product",
                    "ai": "01",
                    "value": "94019097685457"
                },
                {
                    "type": "quantity",
                    "ai": "30",
                    "value": 17
                },
                {
                    "type": "pack_date",
                    "ai": "13",
                    "value": "2017-01-19"
                }
            ]
        },
        {
            "_why": "a count padded, prefixed with FNC1 or ended by one reads the same",
            "rules": "shipped",
            "barcode": "01940190976854573017\u001d13170119",
            "expected": [
                {
                    "type": "product",
                    "ai": "01",
                    "value": "94019097685457"
                },
                {
                    "type": "quantity",
                    "ai": "30",
                    "value": 17
                },
                {
                    "type": "pack_date",
                    "ai": "13",
                    "value": "2017-01-19"
                }
            ]
        },
        {
            "_why": "a date, day 00 being the month's last",
            "rules": "shipped",
            "barcode": "15151020",
            "expected": [
                {
                    "type": "use_date",
                    "ai": "15",
                    "value": "2015-10-20"
                }
            ]
        },
        {
            "_why": "a date, day 00 being the month's last",
            "rules": "shipped",
            "barcode": "15520300",
            "expected": [
                {
                    "type": "use_date",
                    "ai": "15",
                    "value": "2052-03-31"
                }
            ]
        },
        {
            "_why": "a date, day 00 being the month's last",
            "rules": "shipped",
            "barcode": "15200200",
            "expected": [
                {
                    "type": "use_date",
                    "ai": "15",
                    "value": "2020-02-29"
                }
            ]
        },
        {
            "_why": "a yards length reads through the yards rule",
            "rules": "shipped",
            "barcode": "3232000125",
            "expected": [
                {
                    "type": "quantity",
                    "ai": "3232",
                    "value": 1.25
                }
            ]
        },
        {
            "_why": "without the separator configured, '#' ends nothing",
            "rules": "shipped",
            "barcode": "2112345#15090101",
            "expected": null
        },
        {
            "_why": "a configured separator ends a variable-length field",
            "rules": "shipped",
            "separator": "#",
            "barcode": "2112345#15090101",
            "expected": [
                {
                    "type": "lot",
                    "ai": "21",
                    "value": "12345"
                },
                {
                    "type": "use_date",
                    "ai": "15",
                    "value": "2009-01-01"
                }
            ]
        },
        {
            "_why": "the AI's last digit places the decimals only where the rule says so",
            "rules": "decimals",
            "barcode": "30000000",
            "expected": [
                {
                    "type": "quantity",
                    "ai": "300",
                    "value": 0
                }
            ]
        },
        {
            "_why": "the AI's last digit places the decimals only where the rule says so",
            "rules": "decimals",
            "barcode": "30018789",
            "expected": [
                {
                    "type": "quantity",
                    "ai": "300",
                    "value": 18789
                }
            ]
        },
        {
            "_why": "the AI's last digit places the decimals only where the rule says so",
            "rules": "decimals",
            "barcode": "3001515000",
            "expected": [
                {
                    "type": "quantity",
                    "ai": "300",
                    "value": 1515000
                }
            ]
        },
        {
            "_why": "the AI's last digit places the decimals only where the rule says so",
            "rules": "decimals",
            "barcode": "30400000",
            "expected": [
                {
                    "type": "quantity",
                    "ai": "304",
                    "value": 0
                }
            ]
        },
        {
            "_why": "the AI's last digit places the decimals only where the rule says so",
            "rules": "decimals",
            "barcode": "30418789",
            "expected": [
                {
                    "type": "quantity",
                    "ai": "304",
                    "value": 1.8789
                }
            ]
        },
        {
            "_why": "the AI's last digit places the decimals only where the rule says so",
            "rules": "decimals",
            "barcode": "3041515000",
            "expected": [
                {
                    "type": "quantity",
                    "ai": "304",
                    "value": 151.5
                }
            ]
        },
        {
            "_why": "decimals used, but the AI names no position: not this rule",
            "rules": "no_decimal_ai",
            "barcode": "1234",
            "expected": null
        }
    ]
}
`);
