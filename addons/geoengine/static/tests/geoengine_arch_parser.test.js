import { makeGeoLogger } from "@geoengine/geo_debug";
import { GeoengineArchParser } from "@geoengine/geoengine/geoengine_arch_parser";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { disableLogging, enableLogging } from "@web/core/debug/debug_logger";

describe("GeoengineArchParser", () => {
    let parser;

    beforeEach(() => {
        parser = new GeoengineArchParser();
    });

    describe("Debug logging", () => {
        test("logs nothing when odoo is undefined", () => {
            const originalOdoo = globalThis.odoo;
            const originalDebug = console.debug;
            let calls = 0;
            console.debug = () => calls++;
            try {
                delete globalThis.odoo;
                expect(() => makeGeoLogger("T")("message")).not.toThrow();
                expect(calls).toBe(0);
            } finally {
                console.debug = originalDebug;
                globalThis.odoo = originalOdoo;
            }
        });

        test("routes through the shared logic channel and only when enabled", () => {
            const originalDebug = console.debug;
            const seen = [];
            console.debug = (...args) => seen.push(args);
            try {
                disableLogging({ persist: false });
                makeGeoLogger("T")("quiet");
                expect(seen.length).toBe(0);

                enableLogging("geoengine.T:logic", { persist: false });
                makeGeoLogger("T")("loud");
                makeGeoLogger("T")("with data", { a: 1 });
                expect(seen.length).toBe(2);
                expect(seen[0][0].replace(/%c/g, "")).toBe("[geoengine.T] logic loud");
                expect(seen[1][4]).toEqual({ a: 1 });
                expect(makeGeoLogger("T").log.ns).toBe("geoengine.T");
            } finally {
                console.debug = originalDebug;
                disableLogging({ persist: false });
            }
        });
    });

    describe("Attribute Extraction", () => {
        test("_extractPaginationAttributes() extracts limit and countLimit", () => {
            const result = parser._extractPaginationAttributes({
                limit: "80",
                count_limit: "1000",
            });
            expect(result.limit).toBe("80");
            expect(result.countLimit).toBe("1000");
            expect(parser._extractPaginationAttributes({})).toEqual({
                limit: null,
                countLimit: null,
            });
        });

        test("parse() reads the IR, an element or a string to the same archInfo", () => {
            const arch = `
                <geoengine limit="80" count_limit="1000" editable="1" webgl_trail="1"
                           features_list="1" features_list_field="name" default_order="name desc"
                           default_group_by="state" class="o_geo" create="0">
                    <field name="name"/>
                    <field name="state" invisible="1"/>
                    <templates>
                        <t t-name="info_box"><field name="name"/></t>
                    </templates>
                </geoengine>`;
            const models = {
                zone: {
                    fields: {
                        id: { type: "integer", string: "ID" },
                        name: { type: "char", string: "Name" },
                        state: { type: "selection", string: "State" },
                    },
                },
            };
            const fromString = parser.parse(arch, models, "zone");
            expect(fromString.limit).toBe(80);
            expect(fromString.countLimit).toBe(1000);
            expect(fromString.editable).toBe(true);
            expect(fromString.webglTrail).toBe(true);
            expect(fromString.featuresList).toBe(true);
            expect(fromString.featuresListField).toBe("name");
            expect(fromString.featuresListGroupBy).toBe(null);
            expect(fromString.trailTimestampsField).toBe("trail_timestamps");
            expect(fromString.defaultOrder).toEqual([{ name: "name", asc: false }]);
            expect(fromString.defaultGroupBy).toBe("state");
            expect(fromString.className).toBe("o_geo");
            expect(fromString.activeActions.create).toBe(false);
            expect(Object.keys(fromString.fieldNodes)).toEqual(["name", "state"]);
            expect(Object.keys(fromString.templateDocs)).toEqual(["info_box"]);
            expect(
                fromString.templateDocs.info_box
                    .querySelector("field")
                    .getAttribute("field_id"),
            ).toBe("name");

            const { templateDocs, ...rest } = fromString;
            const comparable = (info) => {
                const { templateDocs: docs, ...other } = info;
                return { other, xml: docs.info_box.outerHTML };
            };
            const parser2 = new GeoengineArchParser();
            const parser3 = new GeoengineArchParser();
            const element = new DOMParser().parseFromString(
                arch,
                "text/xml",
            ).documentElement;
            expect(comparable(parser2.parse(element, models, "zone"))).toEqual({
                other: rest,
                xml: templateDocs.info_box.outerHTML,
            });
            expect(comparable(parser3.parse(arch, models, "zone"))).toEqual({
                other: rest,
                xml: templateDocs.info_box.outerHTML,
            });
        });
    });
});
