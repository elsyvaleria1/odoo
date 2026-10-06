import { expect, test } from "@odoo/hoot";
import { EpsonPrinter } from "@point_of_sale/app/utils/printer/epson_printer";

test("epson raster rows are byte-aligned for non-multiple-of-8 widths", async () => {
    const printer = new EpsonPrinter({ ip: "192.0.2.1" });
    const canvas = document.createElement("canvas");
    canvas.width = 10;
    canvas.height = 2;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, 10, 2);

    const raster = printer.canvasToRaster(canvas);
    expect(raster.length).toBe(32);
    expect(raster.slice(0, 16)).toBe("1111111111000000");
    expect(raster.slice(16)).toBe("1111111111000000");

    const encoded = Uint8Array.fromBase64(printer.encodeRaster(raster));
    expect([...encoded]).toEqual([0xff, 0b11000000, 0xff, 0b11000000]);
});
