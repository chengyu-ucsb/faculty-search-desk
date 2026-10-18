# Faculty Search Desk · Access and privacy setup

The public website is at https://chengyu-ucsb.github.io/faculty-search-desk/. The private application-data repository is `chengyu-ucsb/faculty-search-private`.

## Connect this browser

1. On GitHub, open **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Select **Only select repositories**, and choose **both** `faculty-search-desk` and `faculty-search-private`. Set a reasonable expiration.
3. Under **Repository permissions**, enable **Contents: Read and write** for both repositories. Enable **Actions: Read and write** if you want to start the public collector from the website.
4. Open the website's **Settings**. Use owner `chengyu-ucsb`, site repository `faculty-search-desk`, private data repository `faculty-search-private`, branch `main`. Paste the token and choose **Save & test**.
5. Confirm the site reports a verified private tracker and the existing applications appear.

The token stays in this browser's local storage, so use a browser/device you control. If the token was previously scoped only to the public repository, update its access or create a replacement token. Never paste the token into a GitHub issue, public commit, or chat.

## Migration complete

The original `faculty-search-desk` repository was renamed to `faculty-search-desk-old` and made **private**. The replacement `faculty-search-desk` repository has clean public history and contains the redesigned website, source code, and public job feed only. `faculty-search-private` contains the migrated tracker and documents.

**Do not rename or replace the new public repository again.** If your browser reports a permission error, the fine-grained token may still be authorized for the **old repository ID**. Visit your token's settings and select the new `faculty-search-desk` plus `faculty-search-private`. You may need to create a replacement token if GitHub does not allow changing its repository selection.

The old archive is restricted from ordinary public access, but preexisting forks or copies cannot be recalled.

## If access fails

- **Read-only / empty applications:** the token may be missing or not authorized for the private repository.
- **401:** token invalid or expired. Replace it.
- **403:** token lacks the necessary repository permissions.
- **404:** repository inaccessible to the token, or the selected repository/branch name is incorrect.
- **Collector not updating:** check the public repository's Actions tab and the most recent *Collect job postings* run.
- **Scanned PDFs:** automatic extraction requires an actual text layer; image-only PDFs are not yet supported.
