{
    "name": "Field Collections, Sales and Fleet Trips",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Goods a customer takes when the salesperson collects the cash sale leave in no trip",
    "description": "A cash sale whose customer takes the goods at once is handed over at the counter or from the salesperson's vehicle, not delivered: its transfer is validated outside any trip even where the operation type asks deliveries to leave in trips, and it needs no photo of a signed slip, the collection's receipt being the customer's acknowledgement.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "account_collection_sale",
        "stock_fleet",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "auto_install": True,
}
