/** @odoo-module native */
import { DocClient } from "@api_doc/doc_client";
import { App, whenReady } from "@odoo/owl";
import { makeAppConfig } from "@web/env";

export async function startDocClient() {
    await whenReady();
    // In the native-ESM (debug) branch the XML templates for this bundle are
    // delivered via a separate <script type="module"> that runs AFTER this one
    // in document order (the esbuild branch inlines them instead).
    // whenReady() resolves on readyState="interactive" (before DOMContentLoaded),
    // so the templates module may still be pending. Wait for the load event
    // (fires after readyState="complete") to guarantee registration is done.
    if (document.readyState !== "complete") {
        await new Promise((resolve) => {
            window.addEventListener("load", resolve, { once: true });
        });
    }
    const app = new App(makeAppConfig(undefined, { name: "DocClient" }));
    app.createRoot(DocClient).mount(document.body);
}

startDocClient();
