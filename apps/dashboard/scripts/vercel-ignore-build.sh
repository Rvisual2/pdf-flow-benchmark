#!/bin/sh
# Vercel's Ignored Build Step: exit 0 skips; exit 1 builds.
# Run from the Vercel project root, apps/dashboard.

if [ -z "$VERCEL_GIT_PREVIOUS_SHA" ]; then
  echo "No previous deployment; build the dashboard."
  exit 1
fi

# Vercel uses shallow clones. Fetch the last deployed commit when necessary.
if ! git cat-file -e "${VERCEL_GIT_PREVIOUS_SHA}^{commit}" 2>/dev/null; then
  if ! git fetch --quiet --depth=1 origin "$VERCEL_GIT_PREVIOUS_SHA"; then
    echo "Unable to compare with the previous deployment; build the dashboard."
    exit 1
  fi
fi

if git diff --quiet "$VERCEL_GIT_PREVIOUS_SHA" HEAD -- .; then
  echo "No dashboard changes; skip the build."
  exit 0
fi

echo "Dashboard changes detected; build the dashboard."
exit 1
