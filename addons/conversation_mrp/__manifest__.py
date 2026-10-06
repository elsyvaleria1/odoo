{
    "name": "Conversations - Manufacturing",
    "version": "19.0.1.1.0",
    "category": "Sales/CRM",
    "sequence": 67,
    "summary": "Add conversation tools for bills of materials and draft manufacturing orders",
    "description": "Registers tools with manager approval categories for creating a bill of materials or a draft manufacturing order from supplied product and quantity information. Bill-of-materials creation refuses missing catalog components. Requires existing products and manufacturing configuration; created production orders still need the normal manufacturing workflow.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "conversation",
        "mrp",
    ],
    "data": [
        "data/conversation_tools.xml",
    ],
    "auto_install": True,
}
