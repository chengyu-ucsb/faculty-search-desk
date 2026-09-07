# Update 1 — fit scoring + visible Delete button

This folder holds only the three files that changed. Do NOT upload anything
else from the original zip: data/feed.json, data/tracker.json and
data/sources.json in your repository now contain your live data.

  index.html            replaces the page
  scripts/collect.py    replaces the collector
  data/profile.json     new — your fit profile (core / related / red-flag terms)

How to apply, on github.com:
1. Open your repository's front page → Add file → Upload files.
2. Drag the three items from this folder — index.html, the data folder, the
   scripts folder — onto the upload area. GitHub replaces the two existing
   files and adds profile.json; everything else stays as it is.
3. Commit changes.
4. Wait a minute, open your site and reload (Ctrl+F5 if it looks unchanged).
5. Discover → Run collector now. A few minutes later reload: postings carry
   a "fit" score and the terms that matched, sorted best first.
6. Settings → Fit profile to adjust the lists; save re-runs the scoring.
