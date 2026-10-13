/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { scrollTo } from "@web/core/utils/dom/scrolling";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class TabEntry extends Component {
    static props = {
        avatarUrl: t.string(),
        extraClass: t.string().optional(""),
        title: t.string(),
        subtitle: t.string().optional(),
        subtitleClass: t.string().optional(""),
        subtitleIcon: t.string().optional(),
        phoneNumber: t.string(),
        record: t.object(),
        section: t.string(),
        slots: t.object(),
    };
    static template = "voip.TabEntry";
    props = useProps(this.constructor.props);

    setup() {
        this.softphone = useService("voip").softphone;
        this.activeRecordRef = elementRef();
        useLayoutEffect(
            (scrollToActiveRecord) => {
                if (!scrollToActiveRecord || !this.activeRecordRef.el) {
                    return;
                }
                scrollTo(this.activeRecordRef.el);
                this.softphone.callSummary.scrollToActiveRecord = false;
            },
            () => [this.softphone.callSummary.scrollToActiveRecord],
        );
        useLayoutEffect(
            (isActiveRecord) => {
                if (!isActiveRecord || !this.activeRecordRef.el) {
                    return;
                }
                scrollTo(this.activeRecordRef.el);
            },
            () => [this.isActiveRecord],
        );
    }

    /** @returns {string} */
    get flagAlt() {
        return _t("%(country)s flag", {
            country: this.props.record.phone_country_id.name,
        });
    }

    /** @returns {boolean} */
    get isActiveRecord() {
        return (
            this.softphone.activeTabSection === this.props.section &&
            this.props.record.eq(this.softphone.activeRecord)
        );
    }

    /** @param {MouseEvent} ev */
    onClickSummary(ev) {
        if (this.isActiveRecord) {
            this.softphone.activeRecord = null;
            this.softphone.activeTabSection = "";
        } else {
            this.softphone.activeTabSection = this.props.section;
            this.softphone.activeRecord = this.props.record;
        }
    }
}
