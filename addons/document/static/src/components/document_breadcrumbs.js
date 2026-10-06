/** @odoo-module native */
import { Breadcrumbs } from "@web/search/breadcrumbs/breadcrumbs";

import { DocumentsCogMenu } from "../views/cog_menu/document_cog_menu.js";

export class DocumentsBreadcrumbs extends Breadcrumbs {
    static components = {
        ...Breadcrumbs.components,
        DocumentsCogMenu,
    };
    static template = "document.Breadcrumbs";
}
