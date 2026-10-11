/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ImportDataColumnError extends Component {
    static template = "ImportDataColumnError";
    static props = { errors: t.array(), fieldInfo: t.object(), resultNames: t.array() };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.state = proxy({
            isExpanded: false,
            moreInfoContent: undefined,
        });
    }
    get moreInfo() {
        const moreInfoObjects = this.props.errors.map((error) => error.moreinfo);
        const moreInfo = moreInfoObjects.length && moreInfoObjects[0];
        if (Array.isArray(moreInfo) && !moreInfo.length) {
            return undefined;
        }
        return moreInfo;
    }
    isErrorVisible(index) {
        return this.state.isExpanded || index < 3;
    }
    onMoreInfoClicked() {
        const moreInfo = this.moreInfo;
        if (this.state.moreInfoContent) {
            this.state.moreInfoContent = undefined;
        } else if (moreInfo instanceof Array) {
            this.state.moreInfoContent = moreInfo;
        } else {
            this.action.doAction(moreInfo);
        }
    }
}
