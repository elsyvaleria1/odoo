import { expect, test } from "@odoo/hoot";
import { PDFIframe } from "@sign/components/sign_request/PDF_iframe";
import { makeMockEnv, onRpc } from "@web/../tests/web_test_helpers";

test("a viewer whose page is gone by the time its styles arrive stops quietly", async () => {
    await makeMockEnv();
    onRpc("/sign/render_assets_pdf_iframe", () => "<style></style>");
    const pdf = new PDFIframe(
        null,
        {},
        {},
        {
            readonly: true,
            signItemTypes: [],
            signItemOptions: [],
            signItems: [],
            radioSets: {},
        },
    );
    // a document with no window: what an iframe's document becomes once the
    // iframe is removed
    pdf.root = document.implementation.createHTMLDocument("left");
    pdf.root.body.innerHTML = '<div class="page" data-page-number="1"></div>';
    await pdf.start();
    expect(pdf.root.defaultView).toBe(null);
});
