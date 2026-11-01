#!/bin/sh
# Run the visual regression tests in Playwright's Linux image, the environment the baselines
# come from (CI runs the same image). Extra arguments go to `playwright test`,
# e.g. tools/visual-tests.sh --update-snapshots
set -e
VERSION=$(node -p "require('@playwright/test/package.json').version")
exec docker run --rm --ipc=host -v "$PWD":/work -v visual-tests-node-modules:/work/node_modules -w /work \
  "mcr.microsoft.com/playwright:v$VERSION-noble" sh -c "npm ci --no-audit --no-fund && npx playwright test $*"
