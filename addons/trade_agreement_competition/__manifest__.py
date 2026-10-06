{
    "name": "Trade Agreement Price Comparison",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Compare agreement line prices with eligible recorded competitor offers",
    "description": "Adds computed market price, comparison scope and percentage gap to agreement lines. Uses the current date, trade direction, company and partner to select eligible recorded offers, with partner, industry and broader market scopes supplied by the competition dependency. Converts prices to the agreement unit and currency. Sales and purchase bridges expose the fields in their forms.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "trade_agreement",
        "trade_competition",
    ],
    "auto_install": True,
}
