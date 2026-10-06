/** @odoo-module native */
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";
import { patch } from "@web/core/utils/patch";

patch(Navbar.prototype, {
    get colorScheme() {
        return cookie.get("pos_color_scheme") || "light";
    },
    toggleColorScheme() {
        cookie.set("pos_color_scheme", this.colorScheme === "dark" ? "light" : "dark");
        browser.location.reload();
    },
});
