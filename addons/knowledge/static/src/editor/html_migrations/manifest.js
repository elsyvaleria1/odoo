/** @odoo-module native */
import { registry } from "@web/core/registry";

const html_upgrade = registry.category("html_editor_upgrade");

html_upgrade
    .category("1.0")
    .add("knowledge", "@knowledge/editor/html_migrations/migration-1.0");

html_upgrade
    .category("2.0")
    .add("knowledge", "@knowledge/editor/html_migrations/migration-2.0");
