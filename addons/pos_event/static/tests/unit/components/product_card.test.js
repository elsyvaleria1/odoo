import { expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";

import { definePosEventModels } from "../data/generate_model_definitions.js";

definePosEventModels();

test("totalTicketSeats: tickets with seats_max=0 show unlimited when event not limited", async () => {
    const store = await setupPosEnv();
    store.addNewOrder();
    const event = store.models["event.event"].get(2);
    const tickets = [store.models["event.event.ticket"].get(2)];
    event.event_ticket_ids = tickets;
    const product = store.models["product.product"].get(106);
    product.event_id = event;
    const comp = await mountWithCleanup(ProductCard, {
        props: {
            product,
            name: product.display_name,
            productId: product.id,
            imageUrl: false,
        },
    });
    expect(comp.totalTicketSeats).toBe(0);
});

test("totalTicketSeats: tickets with seats_max=0 respect event limit when event is limited", async () => {
    const store = await setupPosEnv();
    store.addNewOrder();
    const event = store.models["event.event"].get(3);
    const tickets = [store.models["event.event.ticket"].get(2)];
    event.event_ticket_ids = tickets;
    const product = store.models["product.product"].get(106);
    product.event_id = event;
    const comp = await mountWithCleanup(ProductCard, {
        props: {
            product,
            name: product.display_name,
            productId: product.id,
            imageUrl: false,
        },
    });
    expect(comp.totalTicketSeats).toBe(5);
});

test("totalTicketSeats: tickets with seats_max=0 show sold out only when event has no seats available", async () => {
    const store = await setupPosEnv();
    store.addNewOrder();
    const event = store.models["event.event"].get(4);
    const tickets = [store.models["event.event.ticket"].get(2)];
    event.event_ticket_ids = tickets;
    const product = store.models["product.product"].get(106);
    product.event_id = event;
    const comp = await mountWithCleanup(ProductCard, {
        props: {
            product,
            name: product.display_name,
            productId: product.id,
            imageUrl: false,
        },
    });
    expect(comp.totalTicketSeats).toBe(-1);
});

test("totalTicketSeats: tickets with seats_max>0 work normally", async () => {
    const store = await setupPosEnv();
    store.addNewOrder();
    const event = store.models["event.event"].get(5);
    const product = store.models["product.product"].get(106);
    product.event_id = event;
    const comp = await mountWithCleanup(ProductCard, {
        props: {
            product,
            name: product.display_name,
            productId: product.id,
            imageUrl: false,
        },
    });
    expect(comp.totalTicketSeats).toBe(3);
});
