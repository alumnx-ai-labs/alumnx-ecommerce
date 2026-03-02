# alumnx-ecommerce

This repository is used to demo the PR systems powered by Claude AI.

## 🧪 Testing instructions

- **PR review system:** open or update a pull request and the `claude-pr-review.yml` workflow should comment automatically.
- **Merge conflict system:** create conflicting edits (e.g. change the same line in two branches) and watch the `claude-merge-conflicts.yml` workflow run when the PR is synchronized.
- **QA system:** comment with `hey claude` on any pull request to trigger a helper response.

Feel free to edit this README in a branch and push the changes to trigger the review workflow.