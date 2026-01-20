# RC Alignment Composite Action

Ensures RC patch increments when only fix commits are present by adding a `Release-As` footer to the history, guiding release-please to produce `vX.Y.Z-rc.N+1` over the same base version.

## Inputs

- `target-ref` (string, default: `refs/heads/next`)
  - Full Git ref that this action should run on. Steps are skipped when the current ref doesn't match.

## Outputs

- `next_version`
  - The calculated RC version (e.g., `1.2.3-rc.5`) when only fix commits exist since the last RC tag. Empty when not applicable.

## Requirements

- Workflow must grant write permissions to contents to allow pushing the commit:

```yaml
permissions:
  contents: write
```

- Python 3.x on the runner (the action sets this up via `actions/setup-python`).

### Using `act` locally

When running locally with `act`, pass a `GITHUB_TOKEN` secret and ensure the runner can push:

```bash
act --workflows .github/workflows/rc-alignment-demo.yaml \
  -s GITHUB_TOKEN=ghp_your_token_here
```

The action will automatically reconfigure the `origin` remote to use `https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git` before pushing. If no token is provided, the push step will fail or be skipped depending on remote configuration.

## Example Usage

```yaml
name: RC Alignment
on:
  push:
    branches: [ next ]
permissions:
  contents: write
jobs:
  enforce-rc:e
    runs-on: ubuntu-latest
    steps:
      - name: Align RC version for fixes-only
        uses: ./actions/rc-alignment
        with:
          target-ref: refs/heads/next
```

## What it does

1. Checks out the repository.
2. Locates the latest tag matching `v*-rc*`.
3. Scans commits since that tag:
  - If any `BREAKING CHANGE` is found, it exits and lets release-please handle Major bumps.
  - If any `feat` is found, it performs a Minor bump while keeping PATCH and resets RC to 0 (e.g., `0.1.1-rc.1` → `0.2.1-rc.0`).
  - Otherwise (fixes-only or chores/docs), it keeps the base version and increments RC (e.g., `0.1.1-rc.1` → `0.1.1-rc.2`).
4. Commits an empty change with a `Release-As: <next_version>` footer to enforce the calculated version.
5. Pushes to the current branch.

## Notes

- This action performs a push; ensure your workflow runner has a valid `GITHUB_TOKEN` and correct permissions.
- If the last commit already contains the same `Release-As` footer, it will skip to avoid loops.
