from datetime import timedelta

from lxml import html

from odoo import fields, http
from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged

from odoo.addons.survey.tests import common
from odoo.addons.web.controllers.utils import FRAGMENTS_HEADER


@tagged("post_install", "-at_install")
class TestResultsWidgets(common.TestSurveyCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.form = cls.env["survey.survey"].create(
            {
                "title": "Widgets",
                "access_mode": "public",
                "questions_layout": "one_page",
            }
        )
        cls.band, cls.leaving = cls.env["survey.question"].create(
            [
                {
                    "title": "Band",
                    "survey_id": cls.form.id,
                    "sequence": 1,
                    "question_type": "simple_choice",
                    "suggested_answer_ids": [
                        (0, 0, {"value": "high"}),
                        (0, 0, {"value": "low"}),
                    ],
                },
                {
                    "title": "Leaving",
                    "survey_id": cls.form.id,
                    "sequence": 2,
                    "question_type": "simple_choice",
                    "suggested_answer_ids": [
                        (0, 0, {"value": "yes"}),
                        (0, 0, {"value": "no"}),
                    ],
                },
            ]
        )
        for band, leaving in (("high", "yes"), ("high", "no"), ("low", "no")):
            answer = cls.env["survey.user_input"].create(
                {"survey_id": cls.form.id, "state": "done"}
            )
            for question, value in ((cls.band, band), (cls.leaving, leaving)):
                cls.env["survey.user_input.line"].create(
                    {
                        "user_input_id": answer.id,
                        "question_id": question.id,
                        "answer_type": "suggestion",
                        "suggested_answer_id": question.suggested_answer_ids.filtered(
                            lambda suggested, value=value: suggested.value == value
                        ).id,
                    }
                )

    def setUp(self):
        super().setUp()
        self.authenticate("admin", "admin")

    def _post(self, route, data, fragments=True):
        return self.url_open(
            f"/survey/results/{self.form.id}/{route}",
            data={"csrf_token": http.Request.csrf_token(self), **data},
            headers={FRAGMENTS_HEADER: "1"} if fragments else None,
            allow_redirects=False,
        )

    def _region(self, response, key):
        self.assertEqual(response.status_code, 200, response.text)
        (fragment,) = response.json()["fragments"]
        self.assertEqual(fragment["key"], key)
        return html.fromstring(fragment["html"])

    def test_the_cross_tabulation_is_rendered_by_the_server(self):
        region = self._region(
            self._post(
                "cross_tabulation", {"q_row": self.band.id, "q_col": self.leaving.id}
            ),
            "survey.cross_tabulation_result",
        )

        self.assertEqual(region.xpath("//tbody/tr/th/text()"), ["high", "low"])
        self.assertEqual(
            region.xpath(
                "//thead/tr/th[position() > 1 and position() < last()]/text()"
            ),
            ["yes", "no"],
        )
        self.assertEqual(region.xpath("string(//tfoot//th[last()])").strip(), "3")

    def test_the_same_question_twice_is_refused_in_words(self):
        region = self._region(
            self._post(
                "cross_tabulation", {"q_row": self.band.id, "q_col": self.band.id}
            ),
            "survey.cross_tabulation_result",
        )

        self.assertIn("two different questions", region.text_content())

    def test_without_javascript_the_cross_tabulation_page_draws_it(self):
        response = self._post(
            "cross_tabulation",
            {"q_row": self.band.id, "q_col": self.leaving.id},
            fragments=False,
        )

        self.assertEqual(response.status_code, 303)
        page = html.fromstring(self.url_open(response.headers["Location"]).content)
        self.assertEqual(page.xpath("//tbody/tr/th/text()"), ["high", "low"])

    def test_the_period_comparison_is_rendered_by_the_server(self):
        region = self._region(
            self._post("compare", {"period_a_from": "", "period_b_from": ""}),
            "survey.comparison_result",
        )

        rows = {
            row.xpath("string(td[1])"): row.xpath("string(td[2])")
            for row in region.xpath("//tbody/tr")
        }
        self.assertEqual(rows["Responses"], "3")

    def test_the_results_page_holds_both_forms_and_their_regions(self):
        page = html.fromstring(self.url_open(f"/survey/results/{self.form.id}").content)

        for key in ("survey.cross_tabulation_result", "survey.comparison_result"):
            (form,) = page.xpath(f"//form[@data-fragment-form='{key}']")
            self.assertEqual(form.get("method"), "post")
            self.assertTrue(page.xpath(f"//*[@data-fragment='{key}']"))
        self.assertFalse(page.xpath("//form//form"))

    def test_the_segments_rank_quality_a_column_the_table_does_not_store(self):
        start = fields.Datetime.now() - timedelta(hours=1)
        self.form.user_input_ids.write(
            {"start_datetime": start, "end_datetime": start + timedelta(minutes=5)}
        )

        response = self.url_open(
            f"/survey/results/{self.form.id}/segments",
            data=json_dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"},
        )

        segments = response.json()["result"]
        self.assertEqual(segments["total"], 3)
        self.assertEqual(sum(tier["count"] for tier in segments["quality_tiers"]), 3)

    def test_the_cross_tabulation_is_swapped_in_without_leaving_the_page(self):
        code = """
            (async () => {
                const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const form = document.querySelector(
                    "form[data-fragment-form='survey.cross_tabulation_result']"
                );
                form.querySelector("[name=q_row]").value = "%(row)s";
                form.querySelector("[name=q_col]").value = "%(col)s";
                window.stayedOnPage = true;
                form.querySelector("button[type=submit]").click();
                for (let i = 0; i < 100; i++) {
                    if (document.querySelector("#crossTabResult tbody")) {
                        break;
                    }
                    await wait(100);
                }
                const heads = [
                    ...document.querySelectorAll("#crossTabResult tbody th"),
                ].map((th) => th.textContent.trim());
                if (window.stayedOnPage && heads.join() === "high,low") {
                    console.log("test successful");
                } else {
                    console.error(`no table swapped in place: ${heads}`);
                }
            })();
        """ % {"row": self.band.id, "col": self.leaving.id}
        self.browser_js(
            f"/survey/results/{self.form.id}",
            code,
            ready="document.body.getAttribute('is-ready') === 'true'",
            login="admin",
        )
