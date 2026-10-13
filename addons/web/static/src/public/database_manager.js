// @ts-check
/** @odoo-module native */

import { setupDatabaseManager } from "./database_manager_page.js";


import { Modal } from "bootstrap";

const start = () =>
    setupDatabaseManager(document.body, {
        getModal: (el) => Modal.getOrCreateInstance(el),
    });

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
} else {
    start();
}
