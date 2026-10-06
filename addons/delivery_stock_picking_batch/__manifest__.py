{
    "name": "Carrier-Based Transfer Batching",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Group stock transfer batches by carrier and check batch weight limits",
    "description": "Extends batch grouping and automatic merge criteria with carrier and weight information. Operation-type configuration controls grouping and maximum weight; carrier execution and transfer batching are implemented by the dependencies.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "stock_delivery",
        "stock_picking_batch",
    ],
    "data": [
        "views/stock_picking_type_views.xml",
        "views/stock_picking_batch_views.xml",
    ],
    "auto_install": True,
}
