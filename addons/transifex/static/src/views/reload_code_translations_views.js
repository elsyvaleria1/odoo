/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ListController, listView } from "@web/views/list";

export class TransifexCodeTranslationListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
    }

    async onClickReloadCodeTranslations() {
        await this.orm.call("transifex.code.translation", "reload", [], {});
        browser.location.reload();
    }
}

registry.category("views").add("transifex_code_translation_tree", {
    ...listView,
    Controller: TransifexCodeTranslationListController,
    buttonTemplate: "transifex.CodeTranslationListView.Buttons",
});
