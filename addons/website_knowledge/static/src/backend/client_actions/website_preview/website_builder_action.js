/** @odoo-module native */
import { registry } from "@web/core/registry";

registry
    .category("isTopWindowURL")
    .add(
        "website_knowledge.website_builder_action",
        ({ pathname }) =>
            pathname &&
            (pathname.startsWith("/knowledge/article/") ||
                pathname.includes("/knowledge/home")),
    );
