# Deploy AccountScope (free)

Cloudflare's free plan can't run the Python app (that needs Containers, on the $5/month Workers Paid plan),
so the free setup splits it in two:

- **Cloudflare Worker, free plan** (`cloudflare/worker-free.ts`): your address,
  `https://accountscope.aravind-ff7.workers.dev`, the **D1 database** (all accounts, research, pitches,
  logins) and the 6-hourly scheduler.
- **Render web service, free plan** (`render.yaml`): runs the Python app. It refuses anything that didn't
  come through your workers.dev address, so its own onrender.com address is useless to anyone else.

Render's free server sleeps after 15 minutes without visitors. The next visit shows "AccountScope is
starting" for about a minute. A research run in progress keeps it awake while the page is open.

## 1. Put the code on GitHub (private)

github.com/new → name `accountscope` → **Private** → Create (no README). Then:

```bash
cd ~/Desktop/"draup_personal_ application /accountscope"
git init -b main
git add .
git commit -m "AccountScope"
git remote add origin https://github.com/YOUR-GITHUB-NAME/accountscope.git
git push -u origin main
```

`.env`, your database and `.venv` are in `.gitignore`, so your keys and data are not uploaded.
Check with `git status` before pushing if you're unsure.

## 2. Run the setup script

```bash
source .venv/bin/activate
python scripts/deploy_free.py
```

It deploys the Worker, shows a token and the list of values to paste into Render, then waits.

## 3. Create the Render service

dashboard.render.com → sign in with GitHub → **New → Blueprint** → pick the `accountscope` repo.
Render reads `render.yaml` and asks for the values the script showed. Apply, wait for **Live**
(5–10 minutes), copy the `https://….onrender.com` address and paste it into the waiting script.
The script connects everything, checks it works, and offers to copy your Mac's accounts.

## Updating later

```bash
./ship.sh "what you changed"
```

It rebuilds the screens if needed, runs the tests, pushes to GitHub (Render redeploys the app server) and
deploys the Cloudflare Worker (which serves the screens and your link).

## Speed

- The screens are served by Cloudflare itself, so the app opens instantly.
- The scheduler pings the app server every 10 minutes, so Render's free plan never puts it to sleep
  (one always-on server fits in Render's 750 free hours a month).
- The busiest read-only screens (accounts list, an account's page, research progress, home summary, alerts) are
  answered by the Worker itself, right next to D1, in two or three batched queries (`cloudflare/fast.ts`).
  Through the app server the same page took ~30 queries, each a trip over the internet. Responses from the
  Worker carry the header `x-served-by: worker`. If one of these handlers fails, the request goes to the app
  server as before.
- Database reads are remembered for 20 seconds (any change clears them), because every query to D1 is a trip
  over the internet. Set `D1_CACHE_SECONDS` in Render to change it, or `0` to turn it off.

Limits: Cloudflare's free plan allows 100,000 requests a day (each database call counts as one).
Render's free server is small (about 0.5 GB memory), so research runs are slower than on your Mac.

---

# Paid alternative: everything on Cloudflare


What runs where:

- **Worker** (`cloudflare/worker.ts`): the public address, `https://accountscope.<your-subdomain>.workers.dev`.
- **Container**: the Python app and the UI. It sleeps after 2 hours with no activity and wakes on the next visit, which takes a few seconds.
- **D1 database** `accountscope`: all accounts, research, pitches and logins. Already created in your account (Asia-Pacific); its ID is in `wrangler.jsonc`.
- **Cron Trigger**: every 6 hours, re-researches watched accounts that are due.

## One-time setup (on your Mac)

You need:

1. **Workers Paid plan** ($5/month): dash.cloudflare.com → Workers & Pages → Plans. Containers need it.
2. **Docker Desktop**, installed and running (docker.com). Wrangler uses it to build the app image.
3. **Node.js 20+** (nodejs.org, or `brew install node`).

Then, in Terminal:

```bash
cd ~/Desktop/draup_personal_*/ && cd accountscope*/
npm install
npx wrangler login                      # opens the browser; approve access
```

Add the secrets. Each command asks you to paste the value; it is stored encrypted in Cloudflare, never in the code:

```bash
npx wrangler secret put OPENAI_API_KEY
npx wrangler secret put TAVILY_API_KEY
npx wrangler secret put APOLLO_API_KEY
npx wrangler secret put ADMIN_EMAIL        # your login email (the platform owner)
npx wrangler secret put ADMIN_PASSWORD     # 10+ chars, upper- and lower-case and a number
openssl rand -hex 32 | npx wrangler secret put INTERNAL_TOKEN   # lets the scheduler start watch runs
```

Deploy (Docker must be running):

```bash
npx wrangler deploy -c wrangler.containers.jsonc
```

The first deploy builds and uploads the image (5–10 minutes). It ends by printing your address,
`https://accountscope.<your-subdomain>.workers.dev`. Open it, wait up to a minute the first time
(the container is starting and creating the tables), and sign in with ADMIN_EMAIL / ADMIN_PASSWORD.
Then change your password from the menu at the bottom left.

## Bring over what you researched on your Mac (optional, once)

After you've signed in once on the cloud site:

```bash
source .venv/bin/activate
python scripts/export_for_d1.py
npx wrangler d1 execute accountscope --remote --file=d1_import.sql
```

Your accounts, research, pitches, decks and "What you sell" land in your own workspace.

## Adding client companies

Menu (bottom left) → **Workspaces** → **New workspace**: the company name plus their admin's email.
You get a temporary password to send them. They sign in, set their own password, and add their team
under **Team**. Each workspace sees only its own accounts, research, profile, decks, pitches and team.
As the owner you can open any workspace from the menu.

## Updating later

Get the new code, then:

```bash
npx wrangler deploy -c wrangler.containers.jsonc
```

## Costs to expect

- Workers Paid: $5/month, which includes some container time.
- Container (basic: 1/4 vCPU, 1 GB) while awake. Billed for active CPU plus memory; idle containers sleep after 2 hours.
- D1: the free allowance (5 GB) is far more than this needs.
- Your OpenAI, Tavily and Apollo usage is billed by them, and all workspaces share your keys.

## Useful commands

```bash
npx wrangler tail                               # live logs
npx wrangler containers list                    # container status
npx wrangler d1 execute accountscope --remote --command "SELECT name FROM workspace"
```

Forgot the owner password? Run
`npx wrangler d1 execute accountscope --remote --command "DELETE FROM auth_session; UPDATE app_user SET active=0 WHERE is_superadmin=1"`,
set a new one with `npx wrangler secret put ADMIN_PASSWORD`, then `npx wrangler deploy -c wrangler.containers.jsonc`. On the next start the
owner account (ADMIN_EMAIL) is restored with the new password. Workspace data isn't touched.
