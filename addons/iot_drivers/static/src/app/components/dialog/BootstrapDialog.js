/** @odoo-module native */
import {
    Component,
    onMounted,
    onWillUnmount,
    signal,
    t,
    useProps,
    xml,
} from "/web/static/lib/owl/owl.es.js";

export class BootstrapDialog extends Component {
    static props = {
        identifier: t.string(),
        slots: t.object(),
        btnName: t.string().optional(),
        isLarge: t.boolean().optional(),
        onOpen: t.function().optional(),
        onClose: t.function().optional(),
    };

    props = useProps(this.constructor.props);

    setup() {
        this.dialog = signal.ref();

        onMounted(() => {
            if (!this.dialog()) {
                return;
            }
            if (this.props.onOpen) {
                this.dialog().addEventListener("show.bs.modal", this.props.onOpen);
            }
            if (this.props.onClose) {
                this.dialog().addEventListener("hide.bs.modal", this.props.onClose);
            }
        });
        onWillUnmount(() => {
            this.dialog()?.removeEventListener("show.bs.modal", this.props.onOpen);
            this.dialog()?.removeEventListener("hide.bs.modal", this.props.onClose);
        });
    }

    static template = xml`
    <t t-translation="off">
        <button type="button" class="btn btn-primary btn-sm" data-bs-toggle="modal" t-att-data-bs-target="'#'+this.props.identifier" t-out="this.props.btnName" />
        <div t-ref="this.dialog" t-att-id="this.props.identifier" class="modal modal-dialog-scrollable fade" t-att-class="{'modal-lg': this.props.isLarge}" tabindex="-1" aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <t t-call-slot="header" />
                    </div>
                    <div class="modal-body position-relative dialog-body">
                        <t t-call-slot="body" />
                    </div>
                    <div class="modal-footer justify-content-around justify-content-md-start flex-wrap gap-1 w-100">
                        <div class="d-flex gap-2">
                            <t t-call-slot="footer" />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </t>
    `;
}
