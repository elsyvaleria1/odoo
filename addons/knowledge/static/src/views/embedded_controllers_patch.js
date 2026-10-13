/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";

export const EmbeddedControllersPatch = (T) =>
    class EmbeddedControllersPatch extends T {
        /**
         * @override
         */
        setup() {
            super.setup(...arguments);
            this.orm = useService("orm");
        }
        /** @override */
        async createRecord() {
            const { onCreate } = this.props.archInfo;
            if (this.canQuickCreate && onCreate === "quick_create") {
                return super.createRecord(...arguments);
            }

            const articleIds = await this.orm.call(
                "knowledge.article",
                "article_create",
                [],
                {
                    is_article_item: true,
                    is_private: false,
                    parent_id: this.props.context.active_id || false,
                },
            );

            this.props.selectRecord(articleIds[0], {});
        }
    };
