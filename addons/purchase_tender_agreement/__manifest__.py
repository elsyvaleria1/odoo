{
    "name": "Purchase Tender Agreement Awards",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Purchase",
    "summary": "Enable purchase tenders to award blanket agreements to winning vendors",
    "description": "Applies the shared tender-agreement mixins to purchase tenders and offers and adds agreement links to the tender view. Selecting the agreements award mode creates confirmed vendor agreements from awarded quantities and net prices; the default award mode remains orders.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "purchase_agreement",
        "purchase_tender",
        "trade_tender_agreement",
    ],
    "data": [
        "views/purchase_tender_views.xml",
    ],
    "auto_install": True,
}
