import { expect, test } from "@odoo/hoot";
import { click, edit } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    makeServerError,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { session } from "@web/session";
import { EmailSharingInput } from "@website_slides/js/public/components/slide_share_dialog/email_sharing_input";

async function send(emails) {
    if (emails) {
        await click(".o_wslides_js_share_email input");
        await edit(emails);
    }
    await click(".o_wslides_js_share_email button");
    await animationFrame();
}

test("an empty field is refused beside it, without asking the server", async () => {
    patchWithCleanup(session, { is_website_user: false });
    onRpc("/slides/slide/send_share_email", () => expect.step("rpc"));
    await mountWithCleanup(EmailSharingInput, { props: { id: 4 } });

    await send("");

    expect(".o_wslides_js_share_email [role=alert]").toHaveText(
        "Please enter valid email(s)",
    );
    expect(".o_wslides_js_share_email input").toHaveClass("is-invalid");
    expect.verifySteps([]);
});

test("addresses the server refuses, or a failed request, are refused beside the field", async () => {
    patchWithCleanup(session, { is_website_user: false });
    let reply = () => false;
    onRpc("/slides/slide/send_share_email", (request) => reply(request));
    await mountWithCleanup(EmailSharingInput, { props: { id: 4 } });

    await send("not-an-address");
    expect(".o_wslides_js_share_email [role=alert]").toHaveCount(1);

    reply = () => {
        throw makeServerError();
    };
    await send(", again");
    expect(".o_wslides_js_share_email [role=alert]").toHaveCount(1);
    expect(".o_wslides_js_share_email input").toHaveClass("is-invalid");
});

test("accepted addresses replace the field with the confirmation", async () => {
    patchWithCleanup(session, { is_website_user: false });
    onRpc("/slides/slide/send_share_email", async (request) => {
        const { params } = await request.json();
        expect.step([params.slide_id, params.emails]);
        return true;
    });
    await mountWithCleanup(EmailSharingInput, { props: { id: 4 } });

    await send("friend@example.com");

    expect.verifySteps([[4, "friend@example.com"]]);
    expect(".o_wslides_js_share_email input").toHaveCount(0);
    expect(".o_wslides_js_share_email .alert-info").toHaveText(
        "Sharing is caring! Your email(s) will arrive shortly.",
    );
});

test("a visitor is asked to log in instead", async () => {
    patchWithCleanup(session, { is_website_user: true });
    await mountWithCleanup(EmailSharingInput, {
        props: { id: 4, category: "document" },
    });

    expect(".o_wslides_js_share_email input").toHaveCount(0);
    expect(".o_wslides_js_share_email .alert-info").toHaveText(
        "Please login to share this document by email.",
    );
});
