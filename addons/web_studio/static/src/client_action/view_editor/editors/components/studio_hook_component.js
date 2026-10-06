/** @odoo-module native */
import { Component, t, useProps, xml } from "@odoo/owl";

const formGrid = xml`
    <div class="o_web_studio_hook"
        t-attf-class="g-col-sm-{{ this.props.colSpan }}"
        t-att-data-xpath="this.props.xpath"
        t-att-data-position="this.props.position"
        t-att-data-type="this.props.type">
            <span class="o_web_studio_hook_separator" />
    </div>
`;

const kanbanAsideHook = xml`
    <div t-attf-class="o_web_studio_hook mx-1 o_web_studio_hook position-absolute top-0 h-100 pe-none w-0 {{ this.props.position === 'before' ? 'start-0' : 'end-0'}}" t-att-data-type="this.props.type" t-att-data-xpath="this.props.xpath" t-att-data-position="this.props.position" data-structures="aside" />
`;

const kanbanRibbon = xml`
    <div class="o_web_studio_hook position-absolute top-0 start-0 h-100 overflow-hidden m-0 p-0 pe-none w-0" t-att-data-type="this.props.type" t-att-data-xpath="this.props.xpath" data-position="inside" data-structures="ribbon">
        <div class="bg-primary opacity-0 position-absolute" style="transform:rotate(45deg); height: 25px; width: 140px; top: 10px; right: -30px;" />
    </div>
`;

const kanbanInline = xml`
    <span class="o_web_studio_hook" t-att-data-xpath="this.props.xpath" t-att-data-position="this.props.position" t-att-data-type="this.props.type" t-att-data-infos="this.props.infos" t-att-data-structures="this.props.structures" />
`;

const defaultTemplate = xml`
<div class="o_web_studio_hook" t-att-data-xpath="this.props.xpath" t-att-data-position="this.props.position" t-att-data-type="this.props.type" t-att-data-infos="this.props.infos" t-att-data-structures="this.props.structures">
    <span class="o_web_studio_hook_separator" />
</div>
`;

export class StudioHook extends Component {
    static template = xml`<t t-call="{{ this.getTemplate(this.props.subTemplate) }}" />`;
    static props = {
        xpath: t.any().optional(),
        position: t.any().optional(),
        type: t.any().optional(),
        colSpan: t.any().optional(),
        subTemplate: t.any().optional(),
        width: t.any().optional(),
        infos: t.any().optional(),
        structures: t.any().optional(),
    };
    static subTemplates = {
        formGrid,
        defaultTemplate,
        kanbanInline,
        kanbanAsideHook,
        kanbanRibbon,
    };
    props = useProps(this.constructor.props);

    getTemplate(templateName) {
        return this.constructor.subTemplates[templateName || "defaultTemplate"];
    }
}
