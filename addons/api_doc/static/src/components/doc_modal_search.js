/** @odoo-module native */
import { useDocModelStore } from "@api_doc/doc_model_store_context";
import { search } from "@api_doc/utils/doc_model_search";
import { Component, onMounted, proxy, t, useListener, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useMountedListener } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";

export class SearchModal extends Component {
    static template = "api_doc.DocSearchModal";

    static components = {};
    static props = { close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.docContext = useDocModelStore();
        this.seachRef = elementRef();
        this.modalRef = elementRef();
        this.scrollRef = elementRef();

        this.results = [];
        this.itemHeight = 45;
        this.itemMargin = 10;

        this.state = proxy({
            resultCount: 0,
            results: [],
            activeFilters: {
                models: true,
                methods: true,
                fields: true,
            },
        });

        this.search = useDebounced((query) => {
            this.results = search(
                this.docContext.modelStore.models,
                query,
                this.state.activeFilters,
            );
            this.state.resultCount = this.results.length;
            this.scrollRef.el.scrollTop = 0;
            this.onScroll(this.scrollRef.el);
        }, 300);

        useListener(window, "keydown", (event) => {
            if (event.key === "Escape") {
                this.props.close();
            }
        });

        useMountedListener(window, "click", (event) => {
            if (!this.modalRef.el.contains(event.target)) {
                this.props.close();
            }
        });

        onMounted(() => {
            this.seachRef.el.focus();
        });
    }

    onInput(event) {
        this.search(event.target.value.trim());
    }

    onSelect(result) {
        this.docContext.modelStore.setActiveModel(result);
        this.props.close();
    }

    onFilterClick(filter) {
        this.state.activeFilters[filter] = !this.state.activeFilters[filter];
        this.search(this.seachRef.el.value.trim());
    }

    onScroll(container) {
        const rowHeight = this.itemHeight + this.itemMargin;
        const nodePadding = 10;

        let startIndex = Math.floor(container.scrollTop / rowHeight) - nodePadding;
        startIndex = Math.max(0, startIndex);

        const viewportHeight = container.getBoundingClientRect().height;
        let visibleCount = Math.ceil(viewportHeight / rowHeight) + 2 * nodePadding;
        visibleCount = Math.min(this.results.length - startIndex, visibleCount);

        this.state.scrollHeight = this.results.length * rowHeight;
        this.state.scrollOffsetY = startIndex * rowHeight;
        this.state.results = this.results.slice(startIndex, startIndex + visibleCount);
    }
}
