#!/bin/bash
# Usage: ./update-url.sh https://abc123.serveo.net
# Updates frontend to point to your live Serveo tunnel URL

set -e

if [ -z "$1" ]; then
  echo "Usage: ./update-url.sh <serveo-url>"
  echo "Example: ./update-url.sh https://abc123.serveo.net"
  exit 1
fi

NEW_URL="${1%/}"  # strip trailing slash
APPJS="$(dirname "$0")/frontend/app.js"

echo "→ Updating API URL to: $NEW_URL"

# Replace whatever the current DEFAULT_API line is
sed -i '' "s|const DEFAULT_API = '.*';|const DEFAULT_API = '$NEW_URL';|" "$APPJS"

echo "✅ Updated frontend/app.js"
echo ""
echo "→ Pushing to GitHub (Vercel will auto-deploy in ~30s)..."
cd "$(dirname "$0")"
git add frontend/app.js
git commit -m "chore(demo): set Serveo tunnel URL for hackathon presentation"
git push

echo ""
echo "✅ Done! Check your Vercel URL in ~30 seconds."
echo "   Test backend: curl $NEW_URL/health"
