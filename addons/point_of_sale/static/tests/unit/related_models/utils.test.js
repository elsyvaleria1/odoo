import { describe, expect, test } from "@odoo/hoot";
import {
    convertDateToRaw,
    convertRawToDate,
} from "@point_of_sale/app/models/related_models/utils";

describe("Date conversion utilities", () => {
    const mockModel = { model: "test.model" };

    test("convertRawToDate", () => {
        const rawDate = "2023-12-25";
        const result = convertRawToDate(mockModel, rawDate, "date_field");
        expect(result).toBeInstanceOf(Temporal.PlainDate);
        expect(result.toString()).toBe(rawDate);
        expect(convertRawToDate(mockModel, null, "date_field")).toBe(undefined);
        expect(convertRawToDate(mockModel, undefined, "date_field")).toBe(undefined);
        expect(() => convertRawToDate(mockModel, "invalid", "date_field")).toThrow();
    });

    test("convertDateToRaw", () => {
        const result = convertDateToRaw(Temporal.PlainDate.from("2023-12-25"));
        expect(result).toBe("2023-12-25");
        expect(convertDateToRaw(null)).toBe(undefined);
        expect(convertDateToRaw(undefined)).toBe(undefined);
        expect(convertDateToRaw("2023-12-25")).toBe("2023-12-25");
    });
});
