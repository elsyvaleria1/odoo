// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { cookie, decodeCookieValue, encodeCookieValue } from "@web/core/browser/cookie";

describe.current.tags("headless");

/** @returns {string[]} */
function captureCookieWrites() {
    /** @type {string[]} */
    const writes = [];
    let raw = "";
    patchWithCleanup(cookie, {
        get _cookieMonster() {
            return raw;
        },
        set _cookieMonster(value) {
            writes.push(value);
            raw = value;
        },
    });
    return writes;
}

test("set writes a well-formed name=value cookie", () => {
    const writes = captureCookieWrites();
    cookie.set("a", "b");
    expect(writes.length).toBe(1);
    expect(writes[0]).toMatch(/^a=b; path=\/; max-age=\d+; SameSite=Lax$/);
});

test("set escapes the characters that corrupt the cookie string", () => {
    const writes = captureCookieWrites();
    cookie.set("k", "a;b%c\nd");
    expect(writes[0]).toMatch(/^k=a%3Bb%25c%0Ad; /);
    expect(cookie.get("k")).toBe("a;b%c\nd");
});

const COOKIE_OCTETS = /^[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*$/;

const CLIENT_WRITES = {
    "utm event test": "utm%20event%20test",
    '{"required": true, "optional": false, "ts": 123}':
        "{%22required%22:%20true%2C%20%22optional%22:%20false%2C%20%22ts%22:%20123}",
    "café ☕ 😀": "caf%C3%A9%20%E2%98%95%20%F0%9F%98%80",
    'say "hi"': "say%20%22hi%22",
    "a;b%c\nd": "a%3Bb%25c%0Ad",
    "!#$&'()*+-./:<=>?@[]^_`{|}~": "!#$&'()*+-./:<=>?@[]^_`{|}~",
};

test("set writes every value as RFC 6265 cookie-octets the server decodes", () => {
    const writes = captureCookieWrites();
    for (const [value, written] of Object.entries(CLIENT_WRITES)) {
        cookie.set("k", value);
        expect(writes.at(-1).startsWith(`k=${written}; `)).toBe(true, {
            message: `value ${JSON.stringify(value)}`,
        });
        expect(written).toMatch(COOKIE_OCTETS);
        expect(cookie.get("k")).toBe(value);
    }
});

test("the consent cookie the server reads is written encoded", () => {
    const writes = captureCookieWrites();
    const consent = '{"required": true, "optional": false, "ts": 123}';
    cookie.set("website_cookies_bar", consent);
    expect(writes[0]).toMatch(/^website_cookies_bar=[^ ";,\\]+; path=\//);
    expect(cookie.get("website_cookies_bar")).toBe(consent);
});

test("encodeCookieValue never throws, even on a lone surrogate", () => {
    expect(encodeCookieValue("a\uD800b")).toBe("a%EF%BF%BDb");
});

test("decodeCookieValue reads the forms browsers may still hold", () => {
    const legacy = {
        "utm event test": "utm event test",
        '{"required": true, "optional": false}':
            '{"required": true, "optional": false}',
        "100%": "100%",
        "%zz": "%zz",
        "%C3%28": "%C3%28",
        '"utm event test"': "utm event test",
        '"say \\"hi\\""': 'say "hi"',
        '"1\\0542"': "1,2",
        '"\\303\\251t\\303\\251"': "été",
        '"x" y "z"': '"x" y "z"',
    };
    for (const [stored, value] of Object.entries(legacy)) {
        expect(decodeCookieValue(stored)).toBe(value, {
            message: `stored ${JSON.stringify(stored)}`,
        });
    }
});

test("get decodes a value the server quoted before werkzeug 3.1.9", () => {
    let raw = 'odoo_utm_campaign="utm event test"; other=1';
    patchWithCleanup(cookie, {
        get _cookieMonster() {
            return raw;
        },
        set _cookieMonster(value) {
            raw = value;
        },
    });
    expect(cookie.get("odoo_utm_campaign")).toBe("utm event test");
});

test("get returns legacy raw values with a bare % untouched", () => {
    let raw = "legacy=100%";
    patchWithCleanup(cookie, {
        get _cookieMonster() {
            return raw;
        },
        set _cookieMonster(value) {
            raw = value;
        },
    });
    expect(cookie.get("legacy")).toBe("100%");
});

test("set(key, undefined) does not create an empty-named cookie", () => {
    const writes = captureCookieWrites();
    cookie.set("myKey", undefined);
    expect(writes.length).toBe(1);
    expect(writes[0].startsWith("myKey;")).toBe(false);
    expect(writes[0]).toMatch(/^myKey=; /);
    expect(writes[0]).toMatch(/max-age=0/);
});

test("delete removes the cookie by name", () => {
    const writes = captureCookieWrites();
    cookie.delete("myKey");
    expect(writes[0]).toMatch(/^myKey=; /);
    expect(writes[0]).toMatch(/max-age=0/);
});

test("set escapes the characters that let a key smuggle cookie syntax", () => {
    const writes = captureCookieWrites();
    cookie.set("a=b", "c");
    expect(writes[0].startsWith("a%3Db=c; ")).toBe(true);
    expect(cookie.get("a=b")).toBe("c");
    expect(cookie.get("a")).toBe(undefined);
});

test("a key carrying an attribute separator cannot reach the attribute list", () => {
    const writes = captureCookieWrites();
    cookie.set("victim; Max-Age=0", "v");
    expect(writes[0]).toMatch(
        /^victim%3B%20Max-Age%3D0=v; path=\/; max-age=\d+; SameSite=Lax$/,
    );
    expect(writes[0].split("; ").length).toBe(4);
});

test("keys round-trip through get()", () => {
    captureCookieWrites();
    for (const key of ["plain", "a=b", "a;b", "a b", "a,b", "a%b"]) {
        cookie.set(key, "value");
        expect(cookie.get(key)).toBe("value", {
            message: `key ${JSON.stringify(key)}`,
        });
    }
});

describe("against the real document.cookie jar", () => {
    test("delete really removes the entry", () => {
        cookie.set("gone", "here");
        expect(cookie.get("gone")).toBe("here");
        cookie.delete("gone");
        expect(cookie.get("gone")).toBe(undefined);
        expect(document.cookie).not.toInclude("gone");
    });

    test("cookie attributes are not stored as cookies", () => {
        cookie.set("real", "1");
        expect(document.cookie).toInclude("real=1");
        for (const attribute of ["path", "max-age", "SameSite"]) {
            expect(cookie.get(attribute)).toBe(undefined, {
                message: `${attribute} must not become a cookie`,
            });
        }
        cookie.delete("real");
    });

    test("values survive the round trip whatever they contain", () => {
        for (const value of [
            "a=b",
            "a b",
            "a,b",
            "a;b",
            "a%b",
            'a"b',
            "1=2=3",
            '{"optional": true}',
            "café ☕ 😀",
        ]) {
            cookie.set("probe", value);
            expect(cookie.get("probe")).toBe(value, {
                message: `value ${JSON.stringify(value)}`,
            });
        }
        cookie.delete("probe");
    });

    test("writing a cookie leaves its neighbours alone", () => {
        cookie.set("first", "1");
        cookie.set("second", "2");
        expect([cookie.get("first"), cookie.get("second")]).toEqual(["1", "2"]);
        cookie.delete("first");
        expect([cookie.get("first"), cookie.get("second")]).toEqual([undefined, "2"]);
        cookie.delete("second");
    });
});
