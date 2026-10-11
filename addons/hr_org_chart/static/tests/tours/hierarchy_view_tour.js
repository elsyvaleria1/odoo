import { registry } from "@web/core/registry";

const card = (name) =>
    `.o_hierarchy_node_container:has(.o_hierarchy_node_content:contains('${name}'))`;

registry.category("web_tour.tours").add("hierarchy_view_tour", {
    steps: () => [
        {
            content: "Switch to the hierarchy view",
            trigger: "button.o_switch_view.o_hierarchy",
            run: "click",
        },
        {
            content: "The roots are drawn, and only the roots",
            trigger: `.o_hierarchy_view ${card("Hierarchy Root")}`,
        },
        {
            content: "Unfold the root: its reports are read from the server",
            trigger: `${card("Hierarchy Root")} .o_hierarchy_node_button.btn-primary`,
            run: "click",
        },
        {
            content: "Both reports are drawn",
            trigger: card("Hierarchy Report A"),
        },
        {
            content: "...and so is the second one",
            trigger: card("Hierarchy Report B"),
        },
        {
            content: "Unfold the report that has one of its own",
            trigger: `${card("Hierarchy Report A")} .o_hierarchy_node_button.btn-primary`,
            run: "click",
        },
        {
            content: "The third level is drawn",
            trigger: card("Hierarchy Grandchild"),
        },
        {
            content: "Fold the root again",
            trigger: `${card("Hierarchy Root")} .o_hierarchy_node_button.btn-secondary`,
            run: "click",
        },
        {
            content: "The branch is gone and the root offers to unfold once more",
            trigger: `${card("Hierarchy Root")} .o_hierarchy_node_button.btn-primary`,
        },
    ],
});
