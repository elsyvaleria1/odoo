/** @odoo-module native */
import { registry } from "@web/core/registry";

const commandCategoryRegistry = registry.category("command_categories");
commandCategoryRegistry.add("knowledge_articles", { namespace: "?" }, { sequence: 10 });
commandCategoryRegistry.add("knowledge_extra", { namespace: "?" }, { sequence: 20 });
