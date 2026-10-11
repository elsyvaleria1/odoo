{
    "name": "Tender Agreement Award Infrastructure",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Provide reusable tender awards that create blanket agreements for winners",
    "description": "Adds an optional agreements award mode to adopting tender models; orders remain the default. Creates and confirms one agreement per winning offer with awarded quantities, discounted unit prices and tender dates, then cancels the linked offer while marking its outcome won. Concrete sales or purchase bridges provide the agreement models.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "trade_agreement",
        "trade_tender",
    ],
    "auto_install": True,
}
