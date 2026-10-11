export function onDropdownStatus(status) {
    return [
        {
            trigger: ".delivery-icon-container",
            run: "click",
        },
        {
            trigger: `.urbanpiper-dropdown-container .container-fluid:eq(0) span b:contains("${status}")`,
            run: "click",
        },
    ];
}

export function orderButtonClick(status) {
    return [
        {
            trigger: `.validation > span:contains("${status}")`,
            run: "click",
        },
    ];
}

export function checkNewOrderCount(expectedCount) {
    return [
        {
            trigger: `.delivery-icon-container > div:contains(${expectedCount})`,
        },
    ];
}

export function fetchDeliveryData() {
    return [
        {
            content: "Fetching Delivery order data",
            trigger: ".pos",
            run: async function () {
                const response = await posmodel.data.call(
                    "pos.config",
                    "get_delivery_data",
                    [posmodel.config.id],
                    {},
                );
                posmodel.delivery_order_count = response.delivery_order_count;
                posmodel.delivery_providers = response.delivery_providers;
                posmodel.total_new_order = response.total_new_order;
                posmodel.delivery_providers_active = response.delivery_providers_active;
            },
        },
    ];
}

export function clickPrepTime() {
    return [
        {
            trigger: `.increment-btn`,
            run: "click",
        },
    ];
}

export function orderHasText(orderNumber, text) {
    return [
        {
            trigger: `.ticket-screen .orders tbody .order-row:has(td:contains("${orderNumber}")):has(td:contains("${text}"))`,
        },
    ];
}
