/** @odoo-module native */
import { useVisible } from "@mail/utils/common/hooks";
import { Component, t, useProps } from "@odoo/owl";
/**
 * Generic component that defines the general structure of a softphone tab.
 */
import { ActionButton } from "@voip/softphone/action_button";
import { NoSearchResults } from "@voip/softphone/no_search_results";
import { SearchBar } from "@voip/softphone/search_bar";
import { TabEntry } from "@voip/softphone/tab_entry";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";

export class Tab extends Component {
    static props = {
        extraClass: t.string().optional(""),
        getSectionStyle: t.function().optional(() => (item) => ""),
        itemsBySection: t.instanceOf(Map),
        noEntriesMessage: t.string().optional(_t("Nothing to see here 😔")),
        noSearchResultsMessage: t.string().optional(),
        onClickBack: t.function().optional(),
        onTabEnd: t.function().optional(() => () => {}),
        sectionIcon: t.string().optional(""),
        slots: t.object(),
        state: t.object(),
    };
    static template = "voip.Tab";
    props = useProps(this.constructor.props);

    setup() {
        this.endOfTabRef = elementRef();
        useVisible(this.endOfTabRef, (isVisible) => {
            if (isVisible) {
                this.props.onTabEnd();
            }
        });
    }
}

export const tabComponents = {
    ActionButton,
    NoSearchResults,
    SearchBar,
    Tab,
    TabEntry,
};
