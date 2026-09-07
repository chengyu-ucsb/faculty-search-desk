# Faculty Search Desk

A personal academic job-application tracker that lives entirely in this
repository and is served by GitHub Pages. One HTML file, no build step, no
server, no database. Setup instructions: [SETUP.md](SETUP.md).

## How it works

| Part | What it is | Where it lives |
| --- | --- | --- |
| The page | `index.html` — jobs, materials checklist, interview rounds, documents, discovery inbox | GitHub Pages |
| Your data | `data/tracker.json` — every job, checklist item, interview, note, and document record | this repository |
| Your files | `files/<document>/v<N>/…` — uploaded CVs, statements, cover letters, kept per version | this repository |
| Sources | `data/sources.json` — the boards and feeds the collector watches | this repository |
| The collector | `scripts/collect.py` — a short Python script run by GitHub Actions every morning; writes `data/feed.json` | GitHub Actions |
| Link checks | `data/link-checks.json` — answers to "can this URL be read automatically?" | GitHub Actions |

When you edit something on the page, the page commits the change through the
GitHub API using a fine-grained personal access token that is stored only in
your browser. Without a token the page is read-only.

The collector fetches pages the plain way — no browser, no JavaScript, no
logins — honours `robots.txt`, and reports sites that refuse automated visits
as *blocked* rather than working around them. It never reads your tracker or
your files.

## Privacy

This is a public repository, so the tracker, notes, and uploaded files are
readable by anyone who finds it. Keep anything you would not want public out of
it. The token is never written to the repository. If you ever want the
repository private, GitHub Pages on private repositories requires GitHub Pro;
the page itself works the same either way.

## Moving or restoring

Every save is a commit, so the History of `data/tracker.json` is a full
backup. **Settings → Download tracker.json** on the page gives you a copy;
**Import** merges one back in. The whole folder can be hosted anywhere that
serves static files if GitHub Pages ever stops being the right home.
