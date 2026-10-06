/** @odoo-module native */
import { setIntersectionObserver } from "@knowledge/js/knowledge_utils";
import { Component, onMounted, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

export class WithLazyLoading extends Component {
    static template = "knowledge.WithLazyLoading";
    static props = { slots: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.loader = elementRef();
        this.state = proxy({ isLoaded: false });

        onMounted(() => {
            const { el } = this.loader;
            this.observer = setIntersectionObserver(el, () => {
                this.state.isLoaded = true;
            });
        });

        onWillUnmount(() => {
            this.observer.disconnect();
        });
    }
}
