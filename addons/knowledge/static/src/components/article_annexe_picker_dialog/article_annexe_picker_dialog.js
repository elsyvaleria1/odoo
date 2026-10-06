/** @odoo-module native */
import { ArticleAnnexePickerNoContentHelper } from "@knowledge/components/article_annexe_picker_dialog/article_annexe_picker_no_content_helper";
import { ArticleTemplatePickerDialog } from "@knowledge/components/article_template_picker_dialog/article_template_picker_dialog";

export class ArticleAnnexePickerDialog extends ArticleTemplatePickerDialog {
    static components = {
        ...ArticleTemplatePickerDialog.components,
        NoContentHelper: ArticleAnnexePickerNoContentHelper,
    };

    /** @returns {boolean} */
    canDeleteTemplates() {
        return false;
    }
}
