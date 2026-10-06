// @ts-check
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import {
    parseEmail,
    prettifyMessageText,
    trimEmptyBlocksAround,
} from "@mail/utils/common/format";
import { expect, test } from "@odoo/hoot";
import { markup } from "@odoo/owl";
import { makeMockEnv } from "@web/../tests/web_test_helpers";

defineMailModels();

function countMatches(html, re) {
    return (html.match(re) || []).length;
}

test("every occurrence of a repeated mention is linkified (regression: bug F)", async () => {
    await makeMockEnv();
    const result = prettifyMessageText("hi @John and again @John", {
        validMentions: { partners: [{ id: 7, name: "John" }] },
    }).toString();
    expect(countMatches(result, /data-oe-id="7"/g)).toBe(2, {
        message: "both @John mentions should be linkified",
    });
});

test("prefix-colliding mentions do not corrupt each other (regression: bug F)", async () => {
    await makeMockEnv();
    const result = prettifyMessageText("@John and @Jo done", {
        validMentions: {
            partners: [
                { id: 8, name: "Jo" },
                { id: 7, name: "John" },
            ],
        },
    }).toString();
    expect(result).toInclude(">@John</a>", {
        message: "@John must be linkified intact",
    });
    expect(result).toInclude(">@Jo</a>", {
        message: "@Jo must be linkified intact",
    });
    expect(result).not.toInclude("</a>hn", {
        message: "@John must not be mangled by the @Jo replacement",
    });
});

test("a mention whose id prefixes another's links each to its own record", async () => {
    await makeMockEnv();
    const result = prettifyMessageText("hi @Al and @Bob, see #General and #Random", {
        validMentions: {
            partners: [
                { id: 1, name: "Al" },
                { id: 12, name: "Bob" },
            ],
            threads: /** @type {any[]} */ ([
                { id: 3, model: "discuss.channel", fullNameWithParent: "General" },
                { id: 31, model: "discuss.channel", fullNameWithParent: "Random" },
            ]),
        },
    }).toString();
    expect(result).toMatch(/data-oe-id="1"[^>]*>@Al<\/a>/);
    expect(result).toMatch(/data-oe-id="12"[^>]*>@Bob<\/a>/);
    expect(result).toMatch(/data-oe-id="3"[^>]*>#General<\/a>/);
    expect(result).toMatch(/data-oe-id="31"[^>]*>#Random<\/a>/);
    expect(result).not.toInclude("mention-");
});

test("mentions of roles whose ids share a prefix stay distinct", async () => {
    await makeMockEnv();
    const result = prettifyMessageText("@Ops then @Sales", {
        validMentions: {
            roles: /** @type {any[]} */ ([
                { id: 2, name: "Ops" },
                { id: 25, name: "Sales" },
            ]),
        },
    }).toString();
    expect(result).toMatch(/data-oe-id="2"[^>]*>@Ops<\/a>/);
    expect(result).toMatch(/data-oe-id="25"[^>]*>@Sales<\/a>/);
});

test("typed placeholder-looking text is not turned into a mention", async () => {
    await makeMockEnv();
    const result = prettifyMessageText("literal @-mention-partner-1 and @Al", {
        validMentions: { partners: [{ id: 1, name: "Al" }] },
    }).toString();
    expect(countMatches(result, /data-oe-id="1"/g)).toBe(1);
    expect(result).toInclude("literal @-mention-partner-1 and");
});

test("parseEmail splits the display name from the first address", () => {
    /** @type {[string, [string, string|false]][]} */
    const cases = [
        ["Name <name@example.com>", ["Name", "name@example.com"]],
        ['"Doe, John" <john@example.com>', ["Doe, John", "john@example.com"]],
        [
            '"john@example.com" <john@example.com>',
            ["john@example.com", "john@example.com"],
        ],
        ["Name<name@example.com>", ["Name", "name@example.com"]],
        ["A <a@x.com>, B <b@y.com>", ["A", "a@x.com"]],
        ["<a@x.com>", ["a@x.com", "a@x.com"]],
        ["John <john@x.com> (work)", ["John", "john@x.com"]],
        ["a@x.com", ["a@x.com", "a@x.com"]],
        ["  a@x.com  ", ["a@x.com", "a@x.com"]],
        ["a@x.com, b@y.com", ["a@x.com", "a@x.com"]],
        ["John Doe john@x.com", ["John Doe", "john@x.com"]],
        ['"Unterminated <u@x.com>', ["Unterminated", "u@x.com"]],
        ["Just a name", ["Just a name", false]],
        ["Name <not an address>", ["Name <not an address>", false]],
    ];
    for (const [text, expected] of cases) {
        expect(parseEmail(text)).toEqual(expected, { message: text });
    }
    expect(parseEmail("")).toBe(undefined);
});

test("parseEmail stays linear on adversarial input", () => {
    const inputs = [
        " <".repeat(2000) + "@",
        "a <" + "@".repeat(20000),
        '"'.repeat(20000),
        '"' + '\\"'.repeat(20000),
        "a".repeat(100000),
        "<".repeat(20000) + "@" + ">".repeat(20000),
        "Name <name@x.com, ".repeat(2000),
    ];
    for (const input of inputs) {
        const start = performance.now();
        parseEmail(input);
        const elapsed = performance.now() - start;
        expect(elapsed).toBeLessThan(50, {
            message: `${JSON.stringify(input.slice(0, 12))}… took ${elapsed.toFixed(1)}ms`,
        });
    }
});

test("trimEmptyBlocksAround drops a trailing block that holds only a line break", () => {
    expect(
        trimEmptyBlocksAround(markup("<p>a</p><p><span><br></span></p>")).toString(),
    ).toBe("<p>a</p>");
    expect(
        trimEmptyBlocksAround(
            markup("<p><br></p><p>a</p><div><b> </b></div>"),
        ).toString(),
    ).toBe("<p>a</p>");
    expect(
        trimEmptyBlocksAround(markup('<p>a</p><p><img src="/x.png"></p>')).toString(),
    ).toBe('<p>a</p><p><img src="/x.png"></p>');
});
