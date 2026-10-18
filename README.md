# Faculty Search Desk

A personal workspace for the academic job market: discover positions, compare research fit, prepare applications, track deadlines, and keep the document versions actually submitted.

**Website:** https://chengyu-ucsb.github.io/faculty-search-desk/

## Features

- **Applications:** searchable job pipeline, deadlines, materials checklists, contacts, interviews, and outcomes.
- **Discover:** daily collection from configured sources, profile-based matching, posting previews, and import into the tracker.
- **Materials:** versioned CVs, statements, job calls, and other application files.
- **Persistence:** private records saved through the GitHub API; public job feeds updated by GitHub Actions.

## Architecture

| Location | Contents | Access |
| --- | --- | --- |
| `faculty-search-desk` | Static website, design, source lists, public job feed, collector | Public |
| `faculty-search-private` | `data/tracker.json` and `files/` (job calls, uploaded documents) | Private |

The public page uses a fine-grained GitHub token stored in the user's browser to access the private repository. Without an authorized token, application records and documents are not readable from the website. The collector reads public sources only; it cannot read your private files.

The token should be restricted to these two repositories. It needs Contents read/write and, for running the public collector from the UI, Actions read/write. Do not commit or share a token.

## Privacy warning: historical public commits

The current public `main` branch **no longer contains the personal tracker or document files**. However, earlier public commits contained those files. They may remain accessible in Git history, cached URLs, forks, or clones. Removing them from today's branch is **not** equivalent to erasing the historical exposure.

To eliminate this repository's public commit-history access while preserving the project URL, archive/rename the old repository and make that archive private, then create a **new clean public repository with the original name**, uploading only the safe public-site files. Inspect copies/forks separately. This operation requires GitHub repository-administration access and is not performed by the website.

See [SETUP.md](SETUP.md) for connecting your browser and finishing the privacy cleanup.

## Development

No build framework or backend server is required.

```bash
pip install -r scripts/requirements.txt
python -m unittest discover -s scripts -p 'test_*.py' -v
node scripts/test_ui.cjs
```

GitHub Actions performs these smoke tests on updates. The collector honors `robots.txt` and records blocked sources rather than circumventing access controls.
