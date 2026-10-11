/** @odoo-module native */
import { Component, t, useProps, xml } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { viewTypeToString } from "@web_studio/studio_service";

export class FieldContentOverlay extends Component {
    static template = xml`
    <div class="position-relative">
      <t t-call-slot="default" />
      <div class="o-web-studio-edit-x2manys-buttons w-100 h-100 d-flex justify-content-center gap-3 position-absolute start-0 top-0 opacity-75 bg-dark" t-if="this.props.displayOverlay" style="z-index: 1000;">
          <button class="btn btn-primary btn-secondary o_web_studio_editX2Many align-self-center"
          t-foreach="['list', 'form']" t-as="vType" t-key="vType"
          t-on-click.stop="() => this.props.onEditViewType(vType)"
          t-att-data-type="vType">
          <t t-out="this.getButtonText(vType)" />
          </button>
      </div>
    </div>`;

    static props = {
        displayOverlay: t.boolean(),
        slots: t.object(),
        onEditViewType: t.function(),
    };
    props = useProps(this.constructor.props);

    getButtonText(viewType) {
        return _t("Edit %s view", viewTypeToString(viewType));
    }
}
