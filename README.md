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

## Privacy status

The original repository has been renamed to **`faculty-search-desk-old`** and made private. A new, clean public repository named **`faculty-search-desk`** hosts this website, with no personal tracker or documents in its commit history. The separate **`faculty-search-private`** repository holds applications and uploaded files.

Previous public clones, cached copies, or forks may still contain information that was public before the archive was made private. Making the old repo private cannot revoke those external copies.

If your browser token was issued before the public repository was recreated, review its **Only select repositories** settings: select the **new** `faculty-search-desk` and `faculty-search-private`, not `faculty-search-desk-old`. See [SETUP.md](SETUP.md).

## Development

No build framework or backend server is required.

```bash
pip install -r scripts/requirements.txt
python -m unittest discover -s scripts -p 'test_*.py' -v
node scripts/test_ui.cjs
```

GitHub Actions performs these smoke tests on updates. The collector honors `robots.txt` and records blocked sources rather than circumventing access controls.
