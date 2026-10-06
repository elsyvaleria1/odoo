import requests

import odoo.tests
from odoo import http
from odoo.tools.misc import file_open

from odoo.addons.html_editor.controllers.main import HTML_Editor
from odoo.addons.web_unsplash.controllers.main import Web_Unsplash


@odoo.tests.common.tagged("post_install", "-at_install")
class TestImageUploadProgress(odoo.tests.HttpCase):
    def test_01_image_upload_progress(self):
        self.start_tour(
            self.env["website"].get_client_action_url("/test_image_progress"),
            "test_image_upload_progress",
            login="admin",
        )

    def test_02_image_upload_progress_unsplash(self):
        BASE_URL = self.base_url()

        @http.route(
            "/html_editor/media_library_search",
            type="jsonrpc",
            auth="user",
            website=True,
        )
        def media_library_search(self, **params):
            return {"results": 0, "media": []}

        # because not preprocessed by ControllerType metaclass
        media_library_search.original_endpoint.routing_type = "json"
        # disable undraw, no third party should be called in tests
        self.patch(HTML_Editor, "media_library_search", media_library_search)

        @http.route("/web_unsplash/fetch_images", type="jsonrpc", auth="user")
        def get_unsplash_images(self, **post):
            return {
                "total": 1434,
                "total_pages": 48,
                "results": [
                    {
                        "id": "HQqIOc8oYro",
                        "alt_description": "brown fox sitting on green grass field during daytime",
                        "urls": {
                            # 'regular': 'https://images.unsplash.com/photo-1462953491269-9aff00919695?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=MnwzMDUwOHwwfDF8c2VhcmNofDF8fGZveHxlbnwwfHx8fDE2MzEwMzIzNDE&ixlib=rb-1.2.1&q=80&w=1080',
                            "regular": BASE_URL
                            + "/website/static/src/img/user-restricted-image.png",
                        },
                        "links": {
                            # 'download_location': 'https://api.unsplash.com/photos/HQqIOc8oYro/download?ixid=MnwzMDUwOHwwfDF8c2VhcmNofDF8fGZveHxlbnwwfHx8fDE2MzEwMzIzNDE'
                            "download_location": BASE_URL
                            + "/website/static/src/img/user-restricted-image.png",
                        },
                        "user": {
                            "name": "Mitchell Admin",
                            "links": {
                                "html": BASE_URL,
                            },
                        },
                    }
                ],
            }

        # because not preprocessed by ControllerType metaclass
        get_unsplash_images.original_endpoint.routing_type = "json"
        # disable undraw, no third party should be called in tests
        self.patch(Web_Unsplash, "get_unsplash_images", get_unsplash_images)
        # the server downloads the chosen image while it answers the browser:
        # fetching it back from this same server needs a second request thread,
        # which a pool sized from a small db_maxconn does not have
        image_url = BASE_URL + "/website/static/src/img/user-restricted-image.png"
        with file_open("website/static/src/img/user-restricted-image.png", "rb") as f:
            image = f.read()
        egress_request = type(self.env["ir.egress"]).request

        def unsplash_download(egress, method, url, *, purpose, **kwargs):
            if purpose != "unsplash":
                return egress_request(egress, method, url, purpose=purpose, **kwargs)
            self.assertEqual(method, "GET")
            self.assertTrue(url.startswith(image_url), url)
            response = requests.Response()
            response.status_code = 200
            response._content = image
            return response

        self.patch(type(self.env["ir.egress"]), "request", unsplash_download)

        self.start_tour(
            self.env["website"].get_client_action_url("/test_image_progress"),
            "test_image_upload_progress_unsplash",
            login="admin",
        )
