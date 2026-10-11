/** @odoo-module native */
/**
 * Golden vectors for the color grammar the image shape protocol uses: what a
 * color literal parses to, the same in the browser (`parseCSSColor`, web's
 * colors.js) and on the server (`parse_css_rgba`, html_editor's
 * ir_attachment.py). `rgba` is null where both refuse the value.
 *
 * Read by:
 *   JS     -> html_editor/static/tests/color_conformance.test.js
 *   Python -> html_editor/tests/test_color_conformance.py, which slices the
 *             template literal below and json.loads it.
 *
 * The payload is a JSON string, not an object literal, so oxfmt leaves it as
 * JSON (see barcodes/static/tests/conformance_vectors.js).
 */

export const VECTORS = JSON.parse(String.raw`
[
    { "value": "#3AADAA", "rgba": [58, 173, 170, 100] },
    { "value": "#fff", "rgba": [255, 255, 255, 100] },
    { "value": "#FfF", "rgba": [255, 255, 255, 100] },
    { "value": "#FFFFFF80", "rgba": [255, 255, 255, 50.19607843137255] },
    { "value": "#ffff", "rgba": null },
    { "value": "#12345", "rgba": null },
    { "value": "#ggg", "rgba": null },
    { "value": "rgb(1,2,3)", "rgba": [1, 2, 3, 100] },
    { "value": "rgb(1, 2, 3)", "rgba": [1, 2, 3, 100] },
    { "value": "rgb(1 2 3)", "rgba": [1, 2, 3, 100] },
    { "value": "rgba(1,2,3,0.5)", "rgba": [1, 2, 3, 50] },
    { "value": "rgba(1,2,3,.25)", "rgba": [1, 2, 3, 25] },
    { "value": "rgba(1,2,3,50%)", "rgba": [1, 2, 3, 50] },
    { "value": "rgba(1,2,3,0.005)", "rgba": [1, 2, 3, 1] },
    { "value": "rgb(1 2 3 / 0.5)", "rgba": [1, 2, 3, 50] },
    { "value": "rgb(0.4,0.6,1.5)", "rgba": [0, 1, 2, 100] },
    { "value": "rgb(255.5,0,0)", "rgba": [256, 0, 0, 100] },
    { "value": "rgb(1000,0,0)", "rgba": [1000, 0, 0, 100] },
    { "value": "rgb(1,2,3", "rgba": null },
    { "value": "rgba(1,2,3,0.5", "rgba": null },
    { "value": "RGB(1,2,3)", "rgba": null },
    { "value": "Rgba(1,2,3,.5)", "rgba": null },
    { "value": "rgb(-1,0,0)", "rgba": null },
    { "value": "rgb(10%,0,0)", "rgba": null },
    { "value": "rgb(1,2)", "rgba": null },
    { "value": " #fff", "rgba": null },
    { "value": "#fff ", "rgba": null },
    { "value": "red", "rgba": null },
    { "value": "transparent", "rgba": null },
    { "value": "currentColor", "rgba": null },
    { "value": "hsl(0,100%,50%)", "rgba": null },
    { "value": "color(srgb 1 0 0)", "rgba": null },
    { "value": "color(display-p3 1 0 0)", "rgba": null },
    { "value": "o-color-1", "rgba": null },
    { "value": "var(--o-color-1)", "rgba": null },
    { "value": "", "rgba": null }
]
`);
