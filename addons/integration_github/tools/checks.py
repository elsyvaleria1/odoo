class ChecksMixin:
    def list_check_runs(self, owner, repo, ref, max_pages=10):
        runs = []
        page = 1
        while page <= max_pages:
            body = self._client.get(
                f"/repos/{owner}/{repo}/commits/{ref}/check-runs",
                params={"per_page": 100, "page": page},
            )["body"]
            batch = body.get("check_runs", [])
            runs.extend(batch)
            if len(runs) >= body.get("total_count", 0) or not batch:
                break
            page += 1
        return runs

    def get_combined_status(self, owner, repo, ref):
        return self._client.get(f"/repos/{owner}/{repo}/commits/{ref}/status")["body"]

    def list_workflow_runs(self, owner, repo, branch=None, head_sha=None, per_page=30):
        params = {"per_page": per_page}
        if branch:
            params["branch"] = branch
        if head_sha:
            params["head_sha"] = head_sha
        return self._client.get(f"/repos/{owner}/{repo}/actions/runs", params=params)[
            "body"
        ].get("workflow_runs", [])

    def compare_commits(self, owner, repo, base, head):
        return self._client.get(f"/repos/{owner}/{repo}/compare/{base}...{head}")[
            "body"
        ]

    def get_ref(self, owner, repo, ref):
        return self._client.get(f"/repos/{owner}/{repo}/git/ref/{ref}")["body"]

    def create_branch(self, owner, repo, branch, sha):
        return self._client.post(
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )["body"]
