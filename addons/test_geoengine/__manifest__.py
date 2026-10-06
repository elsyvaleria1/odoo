{
    "name": "Geoengine Tests",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tests",
    "summary": "Test GeoEngine's fields, domains, I/O, views, tiles and map server on fixture models",
    "description": "Run regression tests for GeoEngine on the models they need, declared here instead of registered by each test: geometry storage, coercion and checks, geo domains and their SQL, I/O round trips, CRS contracts, map access, vector tiles, OGC features, layers, trails, static maps and the map server's query budgets.",
    "author": "Camptocamp,ACSONE SA/NV,Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "depends": [
        "geoengine",
    ],
    "data": [
        "security/ir.access.csv",
    ],
}
