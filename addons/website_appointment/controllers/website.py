from odoo import http

from odoo.addons.website.controllers import main


class Website(main.Website):
    @http.route()
    def autocomplete(
        self,
        search_type=None,
        term=None,
        order=None,
        limit=5,
        max_nb_chars=999,
        options=None,
        offset=0,
    ):
        res = super().autocomplete(
            search_type=search_type,
            term=term,
            order=order,
            limit=limit,
            max_nb_chars=max_nb_chars,
            options=options,
            offset=offset,
        )
        if search_type == "appointments":
            for result in res["results"]:
                if result["name"] and result["detail"]:
                    result["name"] += " (" + result["detail"] + ")"
        return res
