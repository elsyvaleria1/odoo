import { DocumentsModels } from "@document/../tests/helpers/data";
import { expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import { animationFrame, runAllTimers } from "@odoo/hoot-mock";
import { EventBus } from "@odoo/owl";
import {
    contains,
    defineModels,
    makeServerError,
    mockService,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { user } from "@web/core/user";
import { MainComponentsContainer } from "@web/ui/main_components_container";

defineModels(DocumentsModels);

test("Shareable error dialog", async () => {
    expect.errors(1);
    const _bus = new EventBus();
    patchWithCleanup(browser.navigator.clipboard, {
        async writeText(text) {
            expect.step(text);
        },
    });

    mockService("notification", {
        add: (message, options) => {
            expect(message).toBe("The document URL has been copied to your clipboard.");
            expect(options).toEqual({ type: "success" });
            expect.step("Success notification");
        },
    });

    mockService("file_upload", {
        bus: _bus,
        upload: (route, files, params) => {
            if (route === "/documents/upload_traceback") {
                const data = new FormData();
                params?.buildFormData?.(data);
                _bus.trigger("FILE_UPLOAD_LOADED", {
                    upload: {
                        data,
                        response: ["test url"],
                    },
                });
                expect.step("Upload traceback");
            }
        },
    });

    const error = makeServerError({
        subType: "Odoo Client Error",
        message: "Message",
        errorName: "client error",
    });

    await mountWithCleanup(MainComponentsContainer);

    Promise.reject(error);
    await animationFrame();
    expect.verifyErrors(["Message"]);
    expect(".modal-footer button:contains(Close)").toHaveCount(1);
    expect(".modal-footer button:contains(Share)").toHaveCount(1);
    expect(".modal-footer button:contains(Share)").toBeEnabled();
    await contains(".modal-footer button:contains(Share)").click();
    expect(".modal-footer button:contains(Share)").not.toBeEnabled();
    await animationFrame();
    expect.verifySteps(["Upload traceback", "test url", "Success notification"]);
    expect(".modal-footer .o_field_CopyClipboardChar").toHaveCount(1);
    expect(".modal-footer .o_field_CopyClipboardChar").toHaveText("test url");
    await contains(".o_clipboard_button").click();
    await animationFrame();
    expect.verifySteps(["test url"]);
});

test("an unrelated upload does not hijack the traceback link", async () => {
    expect.errors(1);
    const _bus = new EventBus();
    patchWithCleanup(browser.navigator.clipboard, {
        async writeText(text) {
            expect.step(`clipboard:${text}`);
        },
    });
    mockService("notification", {
        add: () => expect.step("notification"),
    });
    mockService("file_upload", {
        bus: _bus,
        upload: (route, files, params) => {
            if (route === "/documents/upload_traceback") {
                const data = new FormData();
                params?.buildFormData?.(data);
                _bus.trigger("FILE_UPLOAD_LOADED", {
                    upload: {
                        data: new FormData(),
                        response: [4242],
                    },
                });
                _bus.trigger("FILE_UPLOAD_LOADED", {
                    upload: { data, response: ["real url"] },
                });
            }
        },
    });

    await mountWithCleanup(MainComponentsContainer);
    Promise.reject(
        makeServerError({
            subType: "Odoo Client Error",
            message: "Message",
            errorName: "client error",
        }),
    );
    await animationFrame();
    expect.verifyErrors(["Message"]);

    await contains(".modal-footer button:contains(Share)").click();
    await animationFrame();
    await runAllTimers();

    expect.verifySteps(["clipboard:real url", "notification"]);
    expect(".modal-footer .o_field_CopyClipboardChar").toHaveText("real url", {
        message: "the unrelated document id never becomes the traceback link",
    });
});

test("Error dialog is not shareable for portal user", async () => {
    expect.errors(1);
    // a portal user sees error dialogs only in debug mode: web swallows them otherwise
    patchWithCleanup(user, { isInternalUser: false });
    patchWithCleanup(odoo, { debug: "1" });
    const error = makeServerError({
        subType: "Odoo Client Error",
        message: "Message",
        errorName: "client error",
    });

    await mountWithCleanup(MainComponentsContainer);

    Promise.reject(error);
    await animationFrame();
    expect.verifyErrors(["Message"]);
    expect(".modal-footer button:contains(Close)").toHaveCount(1);
    expect(".modal-footer button:contains(Share)").toHaveCount(0);
});

test("Multiple error dialogs", async () => {
    expect.errors(3);
    const _bus = new EventBus();
    patchWithCleanup(browser.navigator.clipboard, {
        async writeText(text) {
            expect.step(text);
        },
    });

    mockService("notification", {
        add: (message, options) => {
            expect(message).toBe("The document URL has been copied to your clipboard.");
            expect(options).toEqual({ type: "success" });
            expect.step("Success notification");
        },
    });

    mockService("file_upload", {
        bus: _bus,
        upload: (route, files, params) => {
            if (route === "/documents/upload_traceback") {
                const data = new FormData();
                params?.buildFormData?.(data);
                _bus.trigger("FILE_UPLOAD_LOADED", {
                    upload: {
                        data,
                        response: ["test url"],
                    },
                });
                expect.step("Upload traceback");
            }
        },
    });

    const error1 = makeServerError({
        subType: "Odoo Client Error",
        message: "Message 1",
        errorName: "client error",
    });
    const error2 = makeServerError({
        subType: "Odoo Client Error",
        message: "Message 2",
        errorName: "client error",
    });
    const error3 = makeServerError({
        subType: "Odoo Client Error",
        message: "Message 3",
        errorName: "client error",
    });

    await mountWithCleanup(MainComponentsContainer);

    Promise.reject(error1);
    await runAllTimers();
    await animationFrame();
    expect.verifyErrors(["Message 1"]);
    Promise.reject(error2);
    await runAllTimers();
    await animationFrame();
    expect.verifyErrors(["Message 2"]);
    Promise.reject(error3);
    await runAllTimers();
    await animationFrame();
    expect.verifyErrors(["Message 3"]);
    await contains(".modal-footer button:contains(Share):eq(2)").click();
    expect(".modal-footer button:contains(Share):eq(2)").not.toBeEnabled();
    await animationFrame();
    expect.verifySteps(["Upload traceback", "test url", "Success notification"]);
    expect(".modal-footer .o_field_CopyClipboardChar").toHaveCount(1);
    expect(".modal-footer .o_field_CopyClipboardChar").toHaveText("test url");
    await contains(".o_clipboard_button").click();
    await animationFrame();
    expect.verifySteps(["test url"]);
});

test("two dialogs sharing their tracebacks each get their own link", async () => {
    expect.errors(2);
    const bus = new EventBus();
    patchWithCleanup(browser.navigator.clipboard, { async writeText() {} });
    let uploads = 0;
    mockService("file_upload", {
        bus,
        upload: (route, files, params) => {
            const data = new FormData();
            params?.buildFormData?.(data);
            const url = `url ${++uploads}`;
            bus.trigger("FILE_UPLOAD_LOADED", {
                upload: { data, response: [url] },
            });
        },
    });
    await mountWithCleanup(MainComponentsContainer);
    for (const message of ["First", "Second"]) {
        Promise.reject(
            makeServerError({ subType: "Odoo Client Error", message, errorName: "e" }),
        );
        await animationFrame();
    }
    expect.verifyErrors(["First", "Second"]);
    // the first dialog is covered and inert: the one on top shares, then closes
    await contains(".o_dialog:eq(1) .modal-footer button:contains(Share)").click();
    await animationFrame();
    expect(queryAllTexts(".o_dialog:eq(0) .o_field_CopyClipboardChar")).toEqual([]);
    expect(queryAllTexts(".o_dialog:eq(1) .o_field_CopyClipboardChar")).toEqual([
        "url 1",
    ]);
    await contains(".o_dialog:eq(1) .btn-close").click();
    await contains(".o_dialog .modal-footer button:contains(Share)").click();
    await animationFrame();
    expect(queryAllTexts(".o_dialog .o_field_CopyClipboardChar")).toEqual(["url 2"]);
});

test("a traceback upload that failed can be shared again", async () => {
    expect.errors(1);
    const bus = new EventBus();
    let fail = true;
    mockService("file_upload", {
        bus,
        upload: (route, files, params) => {
            const data = new FormData();
            params?.buildFormData?.(data);
            expect.step(fail ? "upload fails" : "upload succeeds");
            if (fail) {
                bus.trigger("FILE_UPLOAD_ERROR", { upload: { data, state: "error" } });
            } else {
                bus.trigger("FILE_UPLOAD_LOADED", {
                    upload: { data, response: ["url"] },
                });
            }
        },
    });
    const error = makeServerError({
        subType: "Odoo Client Error",
        message: "Message",
        errorName: "client error",
    });
    await mountWithCleanup(MainComponentsContainer);
    Promise.reject(error);
    await animationFrame();
    expect.verifyErrors(["Message"]);
    await contains(".modal-footer button:contains(Share)").click();
    expect(".modal-footer button:contains(Share)").not.toHaveAttribute("disabled");
    fail = false;
    await contains(".modal-footer button:contains(Share)").click();
    await animationFrame();
    expect(".modal-footer button:contains(Share)").toHaveAttribute("disabled");
    expect.verifySteps(["upload fails", "upload succeeds"]);
});
