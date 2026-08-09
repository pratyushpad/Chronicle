# Chronicle — web

Next.js 14 (App Router) frontend for [Chronicle](../README.md): the job feed,
hybrid search UI, company registry, For-You recommendations, saved jobs, and the
application tracker. Deployed on Vercel at
[chronicles-weld.vercel.app](https://chronicles-weld.vercel.app); talks to the
FastAPI backend in [`../api`](../api).

## Development

```bash
npm install
npm run dev     # http://localhost:3000
npm run build   # production build
npm run lint
```

## Environment

Copy [`.env.example`](.env.example) to `.env.local` and fill it in — it needs the
FastAPI base URL (`NEXT_PUBLIC_API_URL`), NextAuth v5 secrets, Google OAuth
credentials, and the internal API secret shared with the backend. The API must be
running (see [`../api`](../api)) for the feed to have data.
