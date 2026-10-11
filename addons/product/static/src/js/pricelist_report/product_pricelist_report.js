/** @odoo-module native */
import { Component, markup, onWillStart, proxy, useProps } from "@odoo/owl";
import { useSetupAction } from "@web/core/action_hook";
import { download } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { KeepLast } from "@web/core/utils/concurrency";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { Layout } from "@web/search/layout";
import { SelectCreateDialog } from "@web/views/view_dialogs";
import { standardActionServiceProps } from "@web/webclient/actions";

export class ProductPricelistReport extends Component {
    static props = { ...standardActionServiceProps };
    static components = { Layout };
    static template = "product.ProductPricelistReport";

    static MAX_QTY = 5;
    props = useProps(this.constructor.props);

    setup() {
        this.config = useViewConfig();
        this.action = useService("action");
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");

        this.renderKeepLast = new KeepLast();
        this.qtyInputRef = elementRef();
        this.formatRef = elementRef();

        const pastState = this.props.state || {};
        const context = this.props.action.context;
        const openedFromPricelist = context.active_model === "product.pricelist";
        const noProducts = pastState.noProducts ?? openedFromPricelist;

        this.activeModel =
            pastState.activeModel ||
            (openedFromPricelist ? "product.template" : context.active_model);
        this.defaultPricelistId = openedFromPricelist ? context.active_id : false;

        this.state = proxy({
            activeIds:
                openedFromPricelist && !pastState.activeIds
                    ? []
                    : pastState.activeIds || context.active_ids || [],
            displayPricelistTitle: pastState.displayPricelistTitle || false,
            html: "",
            noProducts,
            pricelists: [],
            quantities: pastState.quantities || [1, 5, 10],
            selectedPricelist: {},
        });

        onWillStart(async () => {
            this.state.pricelists = await this.getPricelists();
            this.state.selectedPricelist =
                pastState.selectedPricelist ||
                this.pricelists.find((p) => p.id === this.defaultPricelistId) ||
                this.pricelists[0] ||
                {};
            if (this.noProducts && !pastState.noProducts) {
                this.onClickAddProducts();
            }
            await this.renderHtml();
        });

        this.config.setDisplayName(_t("Pricelist Report"));

        useSetupAction({
            getLocalState: () => ({
                displayPricelistTitle: this.displayPricelistTitle,
                quantities: this.quantities,
                selectedPricelist: this.selectedPricelist,
                activeModel: this.activeModel,
                activeIds: this.activeIds,
                noProducts: this.noProducts,
            }),
        });
    }

    get activeIds() {
        return this.state.activeIds;
    }

    get displayPricelistTitle() {
        return this.state.displayPricelistTitle;
    }

    get html() {
        return this.state.html;
    }

    get noProducts() {
        return this.state.noProducts;
    }

    get pricelists() {
        return this.state.pricelists;
    }

    get quantities() {
        return this.state.quantities;
    }

    get reportParams() {
        return {
            active_model: this.activeModel || "product.template",
            active_ids: this.activeIds,
            display_pricelist_title: this.displayPricelistTitle,
            pricelist_id: this.selectedPricelist.id || "",
            quantities: this.quantities.length ? this.quantities : [1],
        };
    }

    get selectedPricelist() {
        return this.state.selectedPricelist;
    }

    getPricelists() {
        return this.orm.searchRead(
            "product.pricelist",
            ["|", ["active", "=", true], ["id", "=", this.defaultPricelistId || 0]],
            ["id", "name"],
            { context: { active_test: false } },
        );
    }

    async renderHtml() {
        if (this.noProducts) {
            this.state.html = "";
            return;
        }
        const html = await this.renderKeepLast.add(
            this.orm.call("report.product.report_pricelist", "get_html", [], {
                data: this.reportParams,
            }),
        );
        this.state.html = markup(html);
    }

    onClickAddQty(ev) {
        ev.preventDefault();

        if (this.quantities.length >= this.constructor.MAX_QTY) {
            this.notification.add(
                _t(
                    "At most %s quantities can be displayed simultaneously. Remove a selected quantity to add others.",
                    this.constructor.MAX_QTY,
                ),
                { type: "warning" },
            );
            return;
        }

        const qty = parseInt(this.qtyInputRef.el?.value, 10);
        if (!Number.isInteger(qty) || qty <= 0) {
            this.notification.add(_t("Please enter a positive whole number."), {
                type: "info",
            });
            return;
        }
        if (this.quantities.includes(qty)) {
            this.notification.add(_t("Quantity already present (%s).", qty), {
                type: "info",
            });
            return;
        }
        this.state.quantities = [...this.quantities, qty].sort((a, b) => a - b);
        this.renderHtml();
    }

    onClickLink(ev) {
        const link = ev.target.closest("a.o_action[data-model][data-res-id]");
        if (!link) {
            return;
        }
        ev.preventDefault();
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: link.dataset.model,
            res_id: parseInt(link.dataset.resId, 10),
            views: [[false, "form"]],
            target: "self",
        });
    }

    async onClickPrint() {
        if (this.noProducts) {
            this.notification.add(_t("Please select some products first."), {
                type: "warning",
            });
            return;
        }
        const selectedFormat = this.formatRef.el?.value;
        if (selectedFormat === "pdf") {
            this.exportPdf();
        } else {
            await this.exportPricelist(selectedFormat);
        }
    }

    exportPdf() {
        this.action.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: "product.report_pricelist",
            report_file: "product.report_pricelist",
            data: this.reportParams,
        });
    }

    async exportPricelist(format) {
        try {
            await download({
                url: `/product/export/pricelist/`,
                data: {
                    report_data: JSON.stringify(this.reportParams),
                    export_format: format,
                },
            });
        } catch (error) {
            console.error(`Error exporting ${format.toUpperCase()} file:`, error);
            this.notification.add(_t("Error exporting file. Please try again."), {
                type: "danger",
            });
        }
    }

    onClickAddProducts() {
        this.dialog.add(SelectCreateDialog, {
            resModel: this.activeModel || "product.template",
            title: _t("Add Products to pricelist report"),
            noCreate: true,
            onSelected: async (resIds) => {
                const added = resIds.filter((id) => !this.activeIds.includes(id));
                if (added.length) {
                    this.state.activeIds = [...this.activeIds, ...added];
                }
                this.state.noProducts = false;
                await this.renderHtml();
            },
        });
    }

    onClickRemoveQty(qty) {
        if (this.quantities.length <= 1) {
            this.notification.add(_t("You must leave at least one quantity."), {
                type: "warning",
            });
            return;
        }
        this.state.quantities = this.quantities.filter((q) => q !== qty);
        this.renderHtml();
    }

    onSelectPricelist(ev) {
        const id = parseInt(ev.target.value, 10);
        this.state.selectedPricelist =
            this.pricelists.find((pricelist) => pricelist.id === id) || {};
        this.renderHtml();
    }

    onToggleDisplayPricelist() {
        this.state.displayPricelistTitle = !this.displayPricelistTitle;
        this.renderHtml();
    }
}

registry.category("actions").add("generate_pricelist_report", ProductPricelistReport);
