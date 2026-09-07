# Putting Faculty Search Desk on GitHub — no terminal needed

Everything below happens on github.com in your browser. Budget about 15 minutes.
Where you see `YOUR-USERNAME`, use your own GitHub username.

## 1. Create the repository

1. Sign in at github.com and open <https://github.com/new>.
2. Repository name: `faculty-search-desk`. Leave the description empty.
3. Choose **Public**.
4. Leave **Add a README file**, **.gitignore**, and **license** unticked — the repository must start empty.
5. Press **Create repository**. You land on an empty-repository page.

## 2. Upload the website files

1. On that empty-repository page, click the small link **uploading an existing file** (in the sentence "Get started by creating a new file or uploading an existing file").
2. In File Explorer open the `website` folder that came with this guide (if you have it as `faculty-search-desk-website.zip`, right-click it → **Extract All…** first, then open the `website` folder inside). Press **Ctrl+A** to select everything inside it (not the folder itself) and drag the selection onto the upload area in the browser. Modern browsers upload the sub-folders too (`.github`, `data`, `files`, `scripts`).
3. Wait until every file is listed. You should see `index.html`, `SETUP.md`, `README.md`, `.nojekyll`, and the folders above. If `.github` or `.nojekyll` did not come along, turn on **View → Show → Hidden items** in File Explorer and drag those two in as well.
4. Scroll down and press **Commit changes**.

If dragging folders does not work in your browser, upload the loose files first, then add the two workflow files by hand: **Add file → Create new file**, type `.github/workflows/collect.yml` as the name, paste the contents of that file from the `website` folder, commit; repeat for `.github/workflows/check-link.yml`.

## 3. Turn on the website

1. In the repository, open **Settings** (the tab on the far right) → **Pages** (left menu).
2. Under **Build and deployment → Source** choose **Deploy from a branch**.
3. Branch: **main**, folder: **/ (root)**. Press **Save**.
4. After a minute, reload the Pages settings page; a box at the top shows your address:
   `https://YOUR-USERNAME.github.io/faculty-search-desk/`. Bookmark it. Opening it now shows the page in read-only mode, which is expected.

## 4. Let the collector write to the repository

1. **Settings → Actions → General**, scroll to **Workflow permissions**.
2. Choose **Read and write permissions** and press **Save**.
3. Open the **Actions** tab. If GitHub asks you to enable workflows, press the green button to enable them. You should see two workflows listed: *Collect job postings* and *Check a link*.

## 5. Make the token the page uses to save your edits

1. Click your profile picture (top right) → **Settings** → scroll the left menu to the very bottom → **Developer settings**.
2. **Personal access tokens → Fine-grained tokens → Generate new token.**
3. Token name: `Faculty Search Desk`. Expiration: pick the longest option offered (you can make a new one when it expires — the page will tell you).
4. **Repository access**: choose **Only select repositories** and pick `faculty-search-desk`.
5. **Permissions → Repository permissions**: set **Contents** to *Read and write* and **Actions** to *Read and write*. Leave everything else at *No access*.
6. Press **Generate token** and copy it right away — it starts with `github_pat_` and GitHub shows it only once.

## 6. Connect the page

1. Open your site address from step 3 and go to **Settings** (top tabs).
2. Owner and Repository should already be filled in from the address. Paste the token and press **Save & test**. You should see "Connected as YOUR-USERNAME … write access confirmed" and the banner at the top disappears.
3. Go to **Discover** and press **Run collector now**. After two or three minutes, reload the page: each source shows whether it was reachable, and new postings appear in the inbox.

That is the whole setup. From now on every edit you make on the page is saved into the repository as a commit, and the collector runs by itself every morning.

## Using it day to day

- **Jobs** — add a position, fill in deadline and materials, move it through stages (preparing → submitted → Zoom → campus → offer) and record the outcome. The "Ready to submit" count tells you which applications are fully prepared.
- **Materials** — drag your CV, statements, and cover letters in. Uploading a file with the same name makes a new version; attach a document to a job's checklist item, and marking that item *Submitted* pins the exact version you sent.
- **Discover** — review new postings, press **Add** to turn one into a job, or **Dismiss**. Paste any board or feed address into **Check a link** and GitHub tells you within a minute whether it can be read automatically; if it can, add it as a source.
- **Phone** — the same address works on your phone; paste the token once there too (it is remembered per browser).

## If something goes wrong

- *"GitHub rejected the token (401)"* — the token was copied incompletely or has expired. Make a new one (step 5) and paste it again.
- *"GitHub refused (403)"* — the token was made without **Contents: Read and write** or **Actions: Read and write**, or for the wrong repository. Edit the token on GitHub or make a new one.
- *Check a link never comes back* — open the **Actions** tab; if the *Check a link* run is red, click it to read the error. If no run appears, Actions may still be disabled (step 4).
- *Sources say "Not checked yet" the day after* — GitHub sometimes delays scheduled runs by an hour or more, and disables schedules on repositories with no commits for 60 days. Any edit on the page counts as a commit, so normal use keeps it alive. **Run collector now** always works immediately.
- *A board shows "Blocked"* — that site refuses automated visits. The collector will not try to get around it; browse that one by hand.
- *Something looks broken after an edit to the files* — the repository keeps every version. On GitHub, open the file, click **History**, and restore an earlier one.
