import { describe, expect, test } from "@odoo/hoot";
import { click, queryAll, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";

setupInteractionWhiteList([
    "mail_group.mail_group_message",
    "mail_group.mail_group_toggle",
    "web.fragment_form",
]);
describe.current.tags("interaction_dev");

const REPLIES_ROUTE = "/groups/list-1/thread-1/get_replies";

/**
 * @param {number} id
 * @param {string} [body]
 * @param {string} [replies]
 */
function message(id, body = "", replies = "") {
    return `
        <li class="d-flex mt-3">
            <div class="flex-grow-1 o_mg_message mw-100" data-test-id="${id}">
                <div class="card"><div class="card-body">
                    <div class="card-text">message ${id}${body}</div>
                    <div class="o_mg_link_parent">
                        <p class="mt8">
                            <a href="#" class="o_mg_link_hide">1 attachments</a>
                            <a href="#" class="o_mg_link_show d-none">1 attachments</a>
                        </p>
                        <div class="o_mg_link_content d-none o_test_attachments"></div>
                    </div>
                </div></div>
                ${
                    replies &&
                    `<div class="o_mg_link_parent">
                        <p class="mt8">
                            <a href="#" class="o_mg_link_hide">replies</a>
                            <a href="#" class="o_mg_link_show d-none">replies</a>
                        </p>
                        <div class="o_mg_link_content o_mg_replies ms-5 d-none">${replies}</div>
                    </div>`
                }
            </div>
        </li>`;
}

/**
 * @param {string} items
 * @param {number} [lastId]
 */
function messagesShort(items, lastId) {
    const more = lastId
        ? `<div class="d-contents" data-fragment="mail_group.replies.1.${lastId}">
                <form method="post" action="${REPLIES_ROUTE}" data-fragment-form="">
                    <input type="hidden" name="last_displayed_id" value="${lastId}"/>
                    <button type="submit" class="btn btn-link o_mg_read_more">more replies</button>
                </form>
            </div>`
        : "";
    return `<div><ul class="list-unstyled">${items}</ul>${more}</div>`;
}

/** @param {(lastId: string) => string} page */
function serveReplies(page) {
    const fetch = browser.fetch;
    patchWithCleanup(browser, {
        fetch: async (url, init) => {
            if (
                new URL(String(url), browser.location.href).pathname !== REPLIES_ROUTE
            ) {
                return fetch(url, init);
            }
            const lastId = /** @type {FormData} */ (init.body).get("last_displayed_id");
            expect.step(`post ${new URL(String(url)).pathname} after ${lastId}`);
            return /** @type {Response} */ ({
                ok: true,
                status: 200,
                headers: new Headers({ "Content-Type": "application/json" }),
                json: async () => ({
                    fragments: [
                        {
                            key: `mail_group.replies.1.${lastId}`,
                            html: `<div class="d-contents" data-fragment="mail_group.replies.1.${lastId}">${page(lastId)}</div>`,
                            swap: "morph",
                        },
                    ],
                    events: [],
                    redirect: null,
                    data: {},
                }),
            });
        },
    });
}

const page = (inner) => `<div class="col-lg-9 o_mg_message">
        <div class="o_mg_replies mt-3">${inner}</div>
    </div>`;

describe("read more replies", () => {
    test("the row asks for the replies after it, and gives way to them and the next row", async () => {
        serveReplies(() => messagesShort(message(3) + message(4), 4));
        await startInteractions(page(messagesShort(message(1) + message(2), 2)));

        await click(".o_mg_read_more");
        await animationFrame();

        expect.verifySteps([`post ${REPLIES_ROUTE} after 2`]);
        expect(
            queryAll(".o_mg_replies ul > li .o_mg_message").map(
                (el) => el.dataset.testId,
            ),
        ).toEqual(["1", "2", "3", "4"]);
        expect(".o_mg_read_more").toHaveCount(1);
        expect("input[name='last_displayed_id']").toHaveValue("4");
    });

    test("an inserted reply is interactive", async () => {
        serveReplies(() => messagesShort(message(3)));
        await startInteractions(page(messagesShort(message(1), 1)));

        await click(".o_mg_read_more");
        await animationFrame();
        expect.verifySteps([`post ${REPLIES_ROUTE} after 1`]);
        await click("[data-test-id='3'] .o_mg_link_hide");
        await animationFrame();

        expect("[data-test-id='3'] .o_test_attachments").not.toHaveClass("d-none");
    });

    test("the row goes when the server has no more replies", async () => {
        serveReplies(() => "");
        await startInteractions(page(messagesShort(message(1), 1)));

        await click(".o_mg_read_more");
        await animationFrame();

        expect.verifySteps([`post ${REPLIES_ROUTE} after 1`]);
        expect(".o_mg_read_more").toHaveCount(0);
        expect(".o_mg_replies ul > li").toHaveCount(1);
    });
});

describe("nested messages", () => {
    test("a toggle opens its own content only", async () => {
        await startInteractions(
            `<ul>${message(1, "", messagesShort(message(2)))}</ul>`,
        );
        const replies = queryOne(
            "[data-test-id='1'] > .o_mg_link_parent > .o_mg_replies",
        );

        await click("[data-test-id='2'] .o_mg_link_hide");
        await animationFrame();

        expect("[data-test-id='2'] .o_test_attachments").not.toHaveClass("d-none");
        expect("[data-test-id='1'] > .card .o_test_attachments").toHaveClass("d-none");
        expect(replies).toHaveClass("d-none");

        await click("[data-test-id='1'] > .o_mg_link_parent > p > .o_mg_link_hide");
        await animationFrame();

        expect(replies).not.toHaveClass("d-none");
        expect("[data-test-id='1'] > .card .o_test_attachments").toHaveClass("d-none");
    });

    test("a quote button belongs to the message that holds the quote", async () => {
        await startInteractions(
            `<ul>${message(1, "", messagesShort(message(2, "<p data-o-mail-quote='1'>quoted</p>")))}</ul>`,
        );

        expect("button.btn-light").toHaveCount(1);
        expect("[data-test-id='2'] button.btn-light").toHaveCount(1);
    });
});
