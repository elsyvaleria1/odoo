import { UploadButton } from "@document_product/js/product_document_kanban/upload_button/upload_button";
import { expect, test } from "@odoo/hoot";

// ---------------------------------------------------------------------------
// UploadButton.validFileType
// ---------------------------------------------------------------------------

/** @param {string} allowed @param {string} type */
function accepts(allowed, type) {
    return UploadButton.prototype.validFileType.call(
        { props: { allowedMIMETypes: allowed }, notification: { add() {} } },
        { type, name: "probe" },
    );
}

test("a type absent from the whitelist is rejected", () => {
    expect(accepts("image/png,image/jpeg", "application/x-msdownload")).toBe(false);
});

test("a file the browser could not type is rejected", () => {
    // "" is what a browser reports for an extension it does not recognise --
    // the exact case a MIME whitelist exists to catch.
    expect(accepts("image/png,image/jpeg", "")).toBe(false);
});

test("a type that is merely a substring of the whitelist is rejected", () => {
    expect(accepts("application/pdf", "application/pd")).toBe(false);
});

test("a whitelisted type is accepted, spacing included", () => {
    expect(accepts("image/png, image/jpeg", "image/jpeg")).toBe(true);
});

test("an accept-style wildcard is honoured", () => {
    expect(accepts("image/*", "image/webp")).toBe(true);
    expect(accepts("image/*", "application/pdf")).toBe(false);
});

test("no whitelist allows everything", () => {
    expect(accepts("", "application/x-msdownload")).toBe(true);
});
