import DocumentViewer from "@mrp_workorder/components/viewer";
import { describe, expect, test } from "@odoo/hoot";
import { manuallyDispatchProgrammaticEvent, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { mockService, mountWithCleanup } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

/** @param {Record<string, any>} props */
async function mountViewer(props) {
    await mountWithCleanup(DocumentViewer, {
        props: { resModel: "quality.point", resId: 1, page: 1, ...props },
    });
}

test("the slides frame is named by a title", async () => {
    await mountViewer({
        resField: "worksheet_google_slide",
        value: "https://docs.google.com/presentation/d/abc/edit",
    });
    const frame = queryOne("iframe.o_embed_iframe");
    expect(frame).toHaveAttribute("title", "Slides viewer");
    expect(frame).not.toHaveAttribute("alt");
});

test("an image that fails to load is reported", async () => {
    mockService("notification", {
        add: (message) => expect.step(String(message)),
    });
    await mountViewer({ resField: "worksheet_image", value: "iVBORw0KGgo" });
    manuallyDispatchProgrammaticEvent(queryOne("img"), "error");
    await animationFrame();
    expect.verifySteps(["Could not display the selected png"]);
});
