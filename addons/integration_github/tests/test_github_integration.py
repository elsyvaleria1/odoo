from unittest.mock import Mock, patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.integration_github.tools import GitHubClient, get_github_client


@tagged("post_install", "-at_install", "integration_github", "github")
class TestGitHubClient(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.cat_custom = cls.env.ref("credential.credential_category_custom")

        cls.github_service = cls.env["integration.service"].search(
            [("code", "=", "github")], limit=1
        )
        if not cls.github_service:
            cls.github_service = cls.env["integration.service"].create(
                {
                    "name": "GitHub",
                    "code": "github",
                    "category": "other",
                    "endpoint_url": "https://api.github.com",
                    "auth_type": "bearer",
                    "environment": "production",
                },
            )

        cls.github_credential = cls.env["credential.credential"].create(
            {
                "name": "GitHub Test Token",
                "endpoint_id": cls.github_service.id,
                "company_id": cls.env.company.id,
                "category_id": cls.cat_custom.id,
                "environment": cls.github_service.environment,
                "credential_value": "ghp_test_token_1234567890",
            },
        )

    def test_github_client_initialization(self):
        github = get_github_client(self.env)

        self.assertIsNotNone(github)
        self.assertIsInstance(github, GitHubClient)
        self.assertEqual(github._client.endpoint_code, "github")

    @patch("requests.Session.request")
    def test_get_repository(self, mock_request):
        mock_response = Mock(headers={"content-type": "application/json"})
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "full_name": "odoo/odoo",
            "description": "Odoo - Open Source ERP",
            "stargazers_count": 30000,
            "forks_count": 15000,
        }
        mock_request.return_value = mock_response

        github = get_github_client(self.env)
        repo = github.get_repository("odoo", "odoo")

        self.assertEqual(repo["full_name"], "odoo/odoo")
        self.assertEqual(repo["stargazers_count"], 30000)
        mock_request.assert_called_once()

    @patch("requests.Session.request")
    def test_list_repositories(self, mock_request):
        mock_response = Mock(headers={"content-type": "application/json"})
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "repo1", "full_name": "org/repo1"},
            {"name": "repo2", "full_name": "org/repo2"},
        ]
        mock_request.return_value = mock_response

        github = get_github_client(self.env)
        repos = github.list_repositories(org="odoo", per_page=10, max_pages=1)

        self.assertEqual(len(repos), 2)
        self.assertEqual(repos[0]["name"], "repo1")

    @patch("requests.Session.request")
    def test_create_repository(self, mock_request):
        mock_response = Mock(headers={"content-type": "application/json"})
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 67890,
            "name": "test-repo",
            "full_name": "user/test-repo",
            "private": False,
        }
        mock_request.return_value = mock_response

        github = get_github_client(self.env)
        repo = github.create_repository(
            name="test-repo",
            description="Test repository",
            private=False,
        )

        self.assertEqual(repo["name"], "test-repo")
        self.assertEqual(repo["private"], False)

    @patch("requests.Session.request")
    def test_list_issues(self, mock_request):
        mock_response = Mock(headers={"content-type": "application/json"})
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"number": 123, "title": "Bug report", "state": "open"},
            {"number": 124, "title": "Feature request", "state": "open"},
        ]
        mock_request.return_value = mock_response

        github = get_github_client(self.env)
        issues = github.list_issues("owner", "repo", state="open", max_pages=1)

        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0]["number"], 123)

    @patch("requests.Session.request")
    def test_create_issue(self, mock_request):
        mock_response = Mock(headers={"content-type": "application/json"})
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 456,
            "title": "New bug",
            "body": "Bug description",
            "state": "open",
        }
        mock_request.return_value = mock_response

        github = get_github_client(self.env)
        issue = github.create_issue(
            "owner",
            "repo",
            title="New bug",
            body="Bug description",
            labels=["bug"],
        )

        self.assertEqual(issue["number"], 456)
        self.assertEqual(issue["title"], "New bug")

    @patch("requests.Session.request")
    def test_create_pull_request(self, mock_request):
        mock_response = Mock(headers={"content-type": "application/json"})
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 789,
            "title": "New feature",
            "head": {"ref": "feature-branch"},
            "base": {"ref": "main"},
            "state": "open",
        }
        mock_request.return_value = mock_response

        github = get_github_client(self.env)
        pr = github.create_pull_request(
            "owner",
            "repo",
            title="New feature",
            head="feature-branch",
            base="main",
        )

        self.assertEqual(pr["number"], 789)
        self.assertEqual(pr["title"], "New feature")

    @patch("requests.Session.request")
    def test_create_webhook(self, mock_request):
        mock_response = Mock(headers={"content-type": "application/json"})
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 111222,
            "url": "https://api.github.com/repos/owner/repo/hooks/111222",
            "config": {"url": "https://odoo.example.com/webhook"},
            "events": ["push", "pull_request"],
            "active": True,
        }
        mock_request.return_value = mock_response

        github = get_github_client(self.env)
        webhook = github.create_webhook(
            "owner",
            "repo",
            url="https://odoo.example.com/webhook",
            events=["push", "pull_request"],
            secret="test_secret",
        )

        self.assertEqual(webhook["id"], 111222)
        self.assertEqual(webhook["active"], True)
        self.assertIn("push", webhook["events"])
