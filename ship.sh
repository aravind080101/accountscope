#!/bin/bash
# Put your changes live: ./ship.sh "what you changed"
#   1. rebuilds the screens if frontend-react/src changed
#   2. runs the tests (stops if any fail)
#   3. pushes to GitHub, which makes Render redeploy the app server
#   4. deploys the Cloudflare Worker, which serves the screens and your link
set -e
cd "$(dirname "$0")"
MSG="${1:-Update}"

if [ -n "$(git status --porcelain frontend-react/src)" ] || [ ! -f frontend-react/dist/index.html ]; then
  echo "▸ Rebuilding the screens…"
  (cd frontend-react && { [ -d node_modules ] || npm install; } && npm run build)
fi

echo "▸ Running the tests…"
[ -f .venv/bin/activate ] && source .venv/bin/activate
python -m pytest -q

echo "▸ Pushing to GitHub (Render redeploys the app server)…"
git add .
git commit -m "$MSG" || echo "  (nothing new to commit)"
git push

echo "▸ Deploying to Cloudflare (screens + your link)…"
npx --yes wrangler deploy

echo
echo "✔ Done. Render takes about 5 minutes to switch over; watch Render → accountscope → Events for 'Live'."
