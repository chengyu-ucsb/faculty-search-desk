# Faculty Search Desk · Access and privacy setup

The public website is at https://chengyu-ucsb.github.io/faculty-search-desk/. The private application-data repository is `chengyu-ucsb/faculty-search-private`.

## Connect this browser

1. On GitHub, open **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Select **Only select repositories**, and choose **both** `faculty-search-desk` and `faculty-search-private`. Set a reasonable expiration.
3. Under **Repository permissions**, enable **Contents: Read and write** for both repositories. Enable **Actions: Read and write** if you want to start the public collector from the website.
4. Open the website's **Settings**. Use owner `chengyu-ucsb`, site repository `faculty-search-desk`, private data repository `faculty-search-private`, branch `main`. Paste the token and choose **Save & test**.
5. Confirm the site reports a verified private tracker and the existing applications appear.

The token stays in this browser's local storage, so use a browser/device you control. If the token was previously scoped only to the public repository, update its access or create a replacement token. Never paste the token into a GitHub issue, public commit, or chat.

## Finish cleaning historical public records

The current public branch no longer has `data/tracker.json` or any uploaded files. **Older commits still expose them.** The cleanest preservation approach is:

1. Confirm the private repository contains the applications and every document. Save a separate backup if desired.
2. Download or locally clone the **current, cleaned public site** (not historical sensitive content).
3. In GitHub repository settings, rename the existing `faculty-search-desk` repository to a distinct archival name and change its visibility to **Private**. This will interrupt the old Pages deployment.
4. Create a **new public repository** named `faculty-search-desk` under the same account. Upload only safe website code, `assets/`, `scripts/`, `.github/`, and public discovery data. Do not upload `data/tracker.json` or `files/`.
5. Enable GitHub Pages on the new repository: **Settings → Pages → Deploy from a branch → main / (root)**.
6. Verify the website at the same project URL and reauthorize your fine-grained token for the newly created public repository if GitHub requires it.

Making the original repository private removes ordinary public access to its history but cannot recall copies already obtained elsewhere. Check public forks and cached references where feasible.

## If access fails

- **Read-only / empty applications:** the token may be missing or not authorized for the private repository.
- **401:** token invalid or expired. Replace it.
- **403:** token lacks the necessary repository permissions.
- **404:** repository inaccessible to the token, or the selected repository/branch name is incorrect.
- **Collector not updating:** check the public repository's Actions tab and the most recent *Collect job postings* run.
- **Scanned PDFs:** automatic extraction requires an actual text layer; image-only PDFs are not yet supported.
