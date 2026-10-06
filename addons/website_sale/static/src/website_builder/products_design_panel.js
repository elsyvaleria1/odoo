/** @odoo-module native */
import { useBuilderContext } from "@html_builder/core/builder_context";
import { BaseOptionComponent } from "@html_builder/core/utils";
import { onMounted, onWillDestroy, proxy, t } from "@odoo/owl";

export class ProductsDesignPanel extends BaseOptionComponent {
    static template = "website_sale.ProductsDesignPanel";
    static components = {
        ...BaseOptionComponent.components,
    };
    static props = {
        label: t.string().optional("Design"),
        recordName: t.string().optional(),
        showLists: t.boolean().optional(true),
        showSecondaryImage: t.boolean().optional(false),
        openByDefault: t.boolean().optional(false),
    };

    setup() {
        super.setup();
        this.builderContext = useBuilderContext();
        this.state = proxy({ overlayVisible: false });
        this.needsDbPersistence = this.props.recordName?.length > 0;

        onMounted(() => {
            this.setupActionConnections();
            this.registerWithPlugin();

            if (this.props.openByDefault) {
                this.openDesignOverlay();
            }
        });

        onWillDestroy(() => {
            this.unregisterFromPlugin();
        });
    }

    registerWithPlugin() {
        const plugin = this.builderContext.editor.shared.productsDesignPanel;
        if (plugin) {
            plugin.registerPanel(this);
        }
    }

    unregisterFromPlugin() {
        const plugin = this.builderContext.editor.shared.productsDesignPanel;
        if (plugin) {
            plugin.unregisterPanel(this);
        }
    }

    setupActionConnections() {
        const builderActions = this.builderContext.editor.shared.builderActions;
        const action = builderActions.getAction("setGap");

        if (action && action.setPanel) {
            action.setPanel(this);
        }
    }

    openDesignOverlay() {
        this.state.overlayVisible = true;
    }

    closeDesignOverlay() {
        this.state.overlayVisible = false;
    }

    onBackdropClick(ev) {
        if (ev.target === ev.currentTarget) {
            this.closeDesignOverlay();
        }
    }
}
