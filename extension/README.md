# Chronicle Autofill — browser extension

Fills Greenhouse, Lever, and Ashby application forms from your Chronicle profile,
and saves roles to your Chronicle tracker in one click.

> **Fill-only, by design.** The extension writes values into form fields and
> **never submits your application**. It contains no `form.submit()` call and never
> clicks a submit button. You review and submit every application yourself.

## What it does

- **Fill this page** — reads your signed-in Chronicle profile (name, email, phone,
  location, links, work authorization) and fills the matching fields on the current
  application page.
- **Save to Chronicle** — adds the current role to your Chronicle application tracker
  (status `saved`), find-or-creating the company/role if Chronicle hasn't ingested it.

Both actions are available from the extension popup and from a small bar injected on
recognized application pages.

## Build

```bash
cd extension
npm install
npm run build        # outputs dist/
npm run typecheck    # optional: tsc --noEmit
```

## Load the unpacked extension (Chrome/Edge/Brave)

1. `npm run build` (produces `extension/dist/`).
2. Open `chrome://extensions`.
3. Toggle **Developer mode** (top-right).
4. Click **Load unpacked** and select the `extension/dist` folder.

## Connect it

1. In the Chronicle web app, go to **Settings → Browser Extension** and click
   **Generate token**. Copy the token (shown once).
2. Open the extension popup → **Connection**:
   - **API endpoint** — your Chronicle API base (default `http://localhost:8002`;
     use your deployed Render URL in production).
   - **Extension token** — paste the token.
   - **Save & connect.** The status chip should show your name.

## Adding another ATS

Field maps live in `src/config/atsMaps.ts` (selectors → logical profile fields) and
URL/identity detection in `src/content/detect.ts`. Adding an ATS is one map entry plus
one detection branch — mirroring the backend adapter pattern. Add its application-page
host to `manifest.json` (`host_permissions` + `content_scripts.matches`).

## Architecture

- `src/background.ts` — the only place that calls the Chronicle API (bearer token from
  `chrome.storage`); running fetches here avoids the job board's page CORS.
- `src/content/` — `detect.ts` (recognize page + extract job identity), `fill.ts`
  (fill-only field writer), `index.ts` (injected bar + popup messaging).
- `src/popup/` — connection status and the Fill / Save controls.
