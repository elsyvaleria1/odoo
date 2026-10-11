/** @odoo-module native */
import { AutoComplete } from "@web/components/autocomplete";

export class PartnerAutoComplete extends AutoComplete {
    setup() {
        super.setup();
        this.shouldSearchWorldwide = false;
    }

    loadOptions(options, request) {
        if (typeof options === "function") {
            return options(request, this.shouldSearchWorldwide);
        }
        return options;
    }

    makeOption(option) {
        const made = super.makeOption(option);
        if (made.data?.isWorldwideAction) {
            made.unselectable = false;
        }
        return made;
    }

    selectOption(option) {
        if (option?.data?.isWorldwideAction) {
            this.searchWorldwide();
            return;
        }
        super.selectOption(option);
    }

    searchWorldwide() {
        this.shouldSearchWorldwide = true;
        this.close();
        this.open(true);
    }

    onInput() {
        this.shouldSearchWorldwide = false;
        return super.onInput();
    }

    cancel() {
        this.shouldSearchWorldwide = false;
        super.cancel();
    }
}
