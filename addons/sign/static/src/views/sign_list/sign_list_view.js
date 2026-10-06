/** @odoo-module native */
import {
    SignListController,
    SignListRenderer,
} from "@sign/views/sign_list/sign_list_controller";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

export const signListView = {
    ...listView,
    Controller: SignListController,
    Renderer: SignListRenderer,
};
registry.category("views").add("sign_list", signListView);
