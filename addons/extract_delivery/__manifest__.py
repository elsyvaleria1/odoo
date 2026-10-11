{
    "name": "Shipping Order Extraction",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Read a carrier's shipping order: tracking number, route, service and amounts",
    "description": "Registers the shipping_order document type for the extraction cascade: the paper a parcel carrier hands over when it takes a shipment (in Mexico an orden de servicio or talón). Two cheap strategies read it before any generative one: the tracking number from the sheet's barcode, matched against the tracking number patterns of the configured carriers, and the route, service, date and amounts from its text. Amounts are checked against each other; the AI extractors, when installed, cover what these leave unread.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "extract",
        "stock_delivery",
    ],
}
