// @ts-check
/** @odoo-module native */

import {
    Component,
    onMounted,
    onWillDestroy,
    onWillStart,
    t,
    useProps,
    xml,
} from "@odoo/owl";
import { DropdownItem } from "@web/components/dropdown/dropdown_item";

export class DropdownPopover extends Component {
    static components = { DropdownItem };
    static template = xml`
        <t t-set="refreshToken" t-value="this.props.refresher.token"/>
        <t t-if="this.props.refresher.items">
            <t t-foreach="this.props.refresher.items" t-as="item" t-key="this.getKey(item, item_index)">
                <DropdownItem class="item.class" onSelected="() => item.onSelected()" t-out="item.label"/>
            </t>
        </t>
        <t t-call-slot="content" />
    `;
    static props = {
        close: t.function().optional(),
        beforeOpen: t.function().optional(),
        onOpened: t.function().optional(),
        onClosed: t.function().optional(),
        refresher: t.object({ token: t.number(), items: t.array().optional() }),
        slots: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        onWillStart(async () => {
            await this.props.beforeOpen?.();
        });

        onMounted(() => {
            this.props.onOpened?.();
        });

        onWillDestroy(() => {
            this.props.onClosed?.();
        });
    }

    /**
     * @param {Record<string, any>} item
     * @param {number} index
     * @returns {string | number}
     */
    getKey(item, index) {
        return "id" in item ? item.id : index;
    }
}
