import { registry } from "@web/core/registry";

const BLOOD = ".o_partner_network_legend_item:has(.o_partner_network_category_blood)";

function nodeCount() {
    return document.querySelectorAll(".o_partner_network_node").length;
}

function checkedKinds() {
    return document.querySelectorAll(".o_partner_network_legend_item input:checked")
        .length;
}

function relatedShown() {
    return Number(
        document
            .querySelector(".o_partner_network_toolbar .text-muted")
            .parentElement.textContent.match(/(\d+) related/)[1],
    );
}

function assertCountsAddUp(where) {
    const counts = [...document.querySelectorAll(".o_partner_network_count")].reduce(
        (sum, node) => sum + Number(node.textContent.trim()),
        0,
    );
    const related = relatedShown();
    if (counts !== related) {
        throw new Error(`${where}: counts sum to ${counts}, header says ${related}`);
    }
}

registry.category("web_tour.tours").add("partner_network_tour", {
    url: "/odoo/action-partner_relationship.action_res_partner_network",
    steps: () => [
        {
            content: "open the seeded contact",
            trigger: ".o_list_view td:contains(Juan Ramirez Solis)",
            run: "click",
        },
        {
            content: "the diagram drew at least one node",
            trigger: ".o_partner_network_canvas .o_partner_network_node",
        },
        {
            content: "the focus is marked",
            trigger: ".o_partner_network_canvas .o_partner_network_focus",
        },
        {
            content: "every category the payload named has a filter",
            trigger: ".o_partner_network_legend .o_partner_network_legend_item",
            run() {
                const kinds = document.querySelectorAll(
                    ".o_partner_network_legend_item",
                ).length;
                if (kinds !== 6) {
                    throw new Error(`${kinds} filters, expected 6`);
                }
                if (checkedKinds() !== 6) {
                    throw new Error("not every kind starts checked");
                }
                assertCountsAddUp("on arrival");
            },
        },
        {
            content: "a category swatch carries a real colour, not the initial value",
            trigger: ".o_partner_network_swatch.o_partner_network_category_blood",
            run() {
                const swatch = document.querySelector(
                    ".o_partner_network_swatch.o_partner_network_category_blood",
                );
                const colour = getComputedStyle(swatch).backgroundColor;
                if (
                    !colour ||
                    colour === "rgba(0, 0, 0, 0)" ||
                    colour === "rgb(0, 0, 0)"
                ) {
                    throw new Error(`blood swatch resolved to ${colour}`);
                }
                const link = document.querySelector(
                    ".o_partner_network_category_blood",
                );
                if (getComputedStyle(link).stroke === "none") {
                    throw new Error("blood link stroke resolved to none");
                }
            },
        },
        {
            content: "the zoom controls are present",
            trigger: ".o_partner_network_toolbar .fa-search-plus",
        },
        {
            content: "the diagram can be recentred",
            trigger: ".o_partner_network_toolbar .fa-crosshairs",
        },
        {
            content: "the diagram has real size on screen",
            trigger: ".o_partner_network_canvas",
            run() {
                const box = this.anchor.getBoundingClientRect();
                if (box.height < 200) {
                    throw new Error(`canvas collapsed to ${box.height}px tall`);
                }
                const drawn = document
                    .querySelector(".o_partner_network_canvas svg")
                    .getBoundingClientRect();
                if (drawn.height < 100 || drawn.width < 100) {
                    throw new Error(`paper drew ${drawn.width}x${drawn.height}`);
                }
                const zoom = document
                    .querySelector(".o_partner_network_zoom")
                    .textContent.trim();
                if (zoom === "20%") {
                    throw new Error("fit clamped to the minimum scale");
                }
                if (this.anchor.closest(".o_partner_network_full")) {
                    const content = document
                        .querySelector(".o_content")
                        .getBoundingClientRect();
                    if (box.width < content.width * 0.9) {
                        throw new Error(
                            `canvas is ${Math.round(box.width)}px wide in ${Math.round(content.width)}px of window`,
                        );
                    }
                    const slack = window.innerHeight - box.bottom;
                    if (slack < 0) {
                        throw new Error(
                            `canvas overruns the window by ${-Math.round(slack)}px`,
                        );
                    }
                    if (slack > 120) {
                        throw new Error(
                            `canvas leaves ${Math.round(slack)}px of the window unused`,
                        );
                    }
                }
                window.__networkNodesBefore = nodeCount();
            },
        },
        {
            content: "no edge label sits on a contact",
            trigger: ".o_partner_network_canvas svg",
            run() {
                const svg = this.anchor;
                const nodes = [...svg.querySelectorAll(".o_partner_network_node")].map(
                    (el) => el.getBoundingClientRect(),
                );
                const labels = [
                    ...svg.querySelectorAll(".o_partner_network_edge_label"),
                ];
                const over = (a, b) =>
                    a.left < b.right &&
                    b.left < a.right &&
                    a.top < b.bottom &&
                    b.top < a.bottom;
                const sitting = labels
                    .filter((el) =>
                        nodes.some((node) => over(el.getBoundingClientRect(), node)),
                    )
                    .map((el) => el.textContent);
                if (sitting.length) {
                    throw new Error(
                        `${sitting.length} of ${labels.length} labels sit on a contact: ${sitting.join(", ")}`,
                    );
                }
                if (!labels.length || !nodes.length) {
                    throw new Error("nothing drawn to check");
                }
            },
        },
        {
            content: "hide the blood ties",
            trigger: `${BLOOD} input`,
            run: "click",
        },
        {
            content: "hiding a kind redraws with fewer contacts",
            trigger: ".o_partner_network_legend_off",
            run() {
                if (!(nodeCount() < window.__networkNodesBefore)) {
                    throw new Error(
                        `hiding blood left ${nodeCount()} nodes, was ${window.__networkNodesBefore}`,
                    );
                }
                if (checkedKinds() !== 5) {
                    throw new Error(`${checkedKinds()} kinds checked, expected 5`);
                }
                assertCountsAddUp("after hiding a kind");
            },
        },
        {
            content: "restore the blood ties",
            trigger: `${BLOOD} input`,
            run: "click",
        },
        {
            content: "the contacts come back",
            trigger: `${BLOOD}:not(.o_partner_network_legend_off)`,
            run() {
                if (nodeCount() !== window.__networkNodesBefore) {
                    throw new Error(
                        `restoring blood gave ${nodeCount()} nodes, expected ${window.__networkNodesBefore}`,
                    );
                }
            },
        },
        {
            content: "with everything checked, All has nothing to do",
            trigger: ".o_partner_network_legend .btn:contains(All)[disabled]",
        },
        {
            content: "clear every kind at once",
            trigger: ".o_partner_network_legend .btn:contains(None)",
            run: "click",
        },
        {
            content: "clearing disables None",
            trigger: ".o_partner_network_legend .btn:contains(None)[disabled]",
        },
        {
            content: "clearing leaves nothing checked",
            trigger: ".o_partner_network_legend",
            run() {
                if (checkedKinds() !== 0) {
                    throw new Error(`${checkedKinds()} kinds still checked after None`);
                }
            },
        },
        {
            content: "bring them all back",
            trigger: ".o_partner_network_legend .btn:contains(All)",
            run: "click",
        },
        {
            content: "restoring every kind restores every contact",
            trigger: ".o_partner_network_canvas .o_partner_network_node",
            run() {
                if (nodeCount() !== window.__networkNodesBefore) {
                    throw new Error(
                        `All gave ${nodeCount()} nodes, expected ${window.__networkNodesBefore}`,
                    );
                }
                assertCountsAddUp("after All");
            },
        },
        {
            content: "isolate a single kind",
            trigger: `${BLOOD} .o_partner_network_only`,
            run: "click",
        },
        {
            content: "only that kind is left checked",
            trigger: ".o_partner_network_legend_off",
            run() {
                if (checkedKinds() !== 1) {
                    throw new Error(`only left ${checkedKinds()} kinds checked`);
                }
                assertCountsAddUp("after only");
                if (!(nodeCount() < window.__networkNodesBefore)) {
                    throw new Error(`only left ${nodeCount()} nodes, expected fewer`);
                }
            },
        },
    ],
});
