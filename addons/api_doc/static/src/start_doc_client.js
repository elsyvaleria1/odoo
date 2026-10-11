/** @odoo-module native */
import { DocClient } from "@api_doc/doc_client";
import { App, whenReady } from "@odoo/owl";
import { makeAppConfig } from "@web/env";

export async function startDocClient() {
    await whenReady();
    if (document.readyState !== "complete") {
        await new Promise((resolve) => {
            window.addEventListener("load", resolve, { once: true });
        });
    }
    const app = new App(makeAppConfig(undefined, { name: "DocClient" }));
    app.createRoot(DocClient).mount(document.body);
}

startDocClient();
