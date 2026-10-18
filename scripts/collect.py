#!/usr/bin/env python3
"""
Faculty Search Desk — job-posting collector.

Reads   data/sources.json      (the boards you follow; edited from the web page)
Writes  data/feed.json         (postings found, plus a status line per source)
        data/link-checks.json  (results of one-off "check this link" requests)

    python scripts/collect.py              # check every enabled source
    python scripts/collect.py --force      # ignore the weekly cadence
    python scripts/collect.py --check URL  # try one URL and record the verdict

Plain HTTP only: no browser, no JavaScript, no logins, no bypassing blocks.
Sites that refuse automated visits are reported as "blocked" and left alone.
robots.txt is honoured.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.robotparser

import feedparser
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from detail_extract import text_lines, application_links, evidence_from_lines, merge_evidence, describe_coverage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_PATH = os.path.join(ROOT, "data", "sources.json")
FEED_PATH = os.path.join(ROOT, "data", "feed.json")
CHECKS_PATH = os.path.join(ROOT, "data", "link-checks.json")
PROFILE_PATH = os.path.join(ROOT, "data", "profile.json")

# Fit scoring: how many individual posting pages to read per run, and how far
# back to re-read postings after the profile changes.
MAX_DETAIL_FETCHES = 60
RESCORE_WINDOW_DAYS = 150
MAX_DETAIL_TRIES = 7
MAX_HOST_FAILURES = 2
DETAIL_TEXT_CAP = 12000
STORED_DETAIL_CAP = 6500
FIT_VERSION = 5

REPO = os.environ.get("GITHUB_REPOSITORY", "faculty-search-desk")
USER_AGENT = f"FacultySearchDesk/1.0 (+https://github.com/{REPO}; personal academic job tracker)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}
TIMEOUT = (10, 30)
MAX_PAGES = 2
MAX_FEED_JOBS = 3000
FEED_RETENTION_DAYS = 150
PAUSE_BETWEEN_REQUESTS = 1.5

JOB_PATH = re.compile(r"/(jobs?|positions?|postings?|vacanc(?:y|ies)|openings?|opportunit(?:y|ies)|jobdetail|job-details?|careers?/[^/]+)(/|\?|$)", re.I)
NOT_A_POSTING = re.compile(r"(search|/rss|login|register|signin|sign-in|alert|employer|post-a-job|postjob|/browse|page=|/category|/categories|/sitemap|/faq|/help|/about|/contact|/terms|/privacy|mailto:|javascript:)", re.I)
GENERIC_ANCHOR = {"apply", "apply now", "view", "view job", "view details", "details", "more", "read more", "learn more", "job details", "see details", "view more"}
BOT_WALL = re.compile(r"(_Incapsula_Resource|incapsula|cf-chl|cf_chl|Just a moment|Attention Required|Access Denied|captcha|Request unsuccessful|Pardon Our Interruption|are you a robot|enable cookies to continue)", re.I)
INSTITUTION_HINT = re.compile(r"(universit|college|institute|school|academy|polytechnic|conservator|hochschule|universidad|université)", re.I)
LOCATION_HINT = re.compile(r"(,\s*[A-Z]{2}\b|\bRemote\b|\bHybrid\b|United States|United Kingdom|Canada|Australia|Qatar|Singapore|Hong Kong|Netherlands|Germany|Denmark|Ireland|New Zealand|Switzerland|Sweden|Norway|Finland|Belgium|Korea|Japan|China)")
DATE_LIKE = re.compile(r"^(posted|closes?|deadline|apply by|expires?)\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}", re.I)
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "source", "src"}


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def normalize_url(url):
    try:
        p = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return url
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    path = p.path or "/"
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, urllib.parse.urlencode(q), ""))


def job_id(url):
    frag = urllib.parse.urlsplit(url).fragment  # wiki entries are one page with many anchors
    return hashlib.sha1((normalize_url(url) + ("#" + frag if frag else "")).encode("utf-8")).hexdigest()[:12]


JOB_NUMBER_LABEL = re.compile(r"\b(?:job|posting|position|requisition|req|vacancy|opening|advert(?:isement)?|competition|tracking|pcn|pin)\s*(?:id|number|no\.?|#|code|ref(?:erence)?\.?)?\s*[:#.]?\s*([A-Z]{0,5}[-_ ]?\d{4,9}(?:[-_][A-Z0-9]{1,6})?)\b", re.I)


def job_number(url="", text=""):
    """The posting's own number ("498438", "R0012345") — two postings from one department differ by it. Text first, then the URL."""
    if text:
        m = JOB_NUMBER_LABEL.search(text[:6000])
        if m and re.search(r"\d{4}", m.group(1)) and not re.fullmatch(r"(?:19|20)\d{2}", m.group(1)):
            return m.group(1).replace(" ", "")
    if url:
        for rx in (r"[?&](?:l?job|req|posting|position|job_?id|jobid|requisition|id)=(\d{4,9})",
                   r"/(?:apply|job|jobs|postings?|positions?|requisitions?|details?)/(?:[A-Za-z-]*-)?(\d{5,9})(?:[/?#]|$)",
                   r"[-/](\d{6,9})(?:[-/?#]|$)"):
            m = re.search(rx, url, re.I)
            if m:
                return m.group(1)
    return ""


def clean_text(s, limit=None):
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return s[:limit] if limit else s


# ----------------------------------------------------------------------------
# fetching
# ----------------------------------------------------------------------------
_robots_cache = {}


def robots_allowed(url):
    """True unless the site's robots.txt disallows this path for us."""
    p = urllib.parse.urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers=HEADERS, timeout=(5, 10))
            if r.status_code == 200 and r.text:
                rp.parse(r.text.splitlines())
            else:
                rp = None
        except requests.RequestException:
            rp = None
        _robots_cache[base] = rp
    rp = _robots_cache[base]
    if rp is None:
        return True
    return rp.can_fetch("FacultySearchDesk", url) and rp.can_fetch("*", url)


def fetch(url):
    """Return dict(status, text, content_type, final_url, error, blocked)."""
    out = {"status": None, "text": "", "content_type": "", "final_url": url, "error": None, "blocked": False}
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        out["status"] = r.status_code
        out["final_url"] = r.url
        out["content_type"] = (r.headers.get("Content-Type") or "").lower()
        if r.status_code == 200 and ("application/pdf" in out["content_type"] or r.content.startswith(b"%PDF")):
            if len(r.content) > 8_000_000:
                out["error"] = "PDF exceeds 8 MB extraction limit"
                return out
            try:
                reader = PdfReader(io.BytesIO(r.content))
                out["text"] = "\n".join(page.extract_text() or "" for page in reader.pages[:35])[:3_000_000]
                out["content_type"] = "application/pdf"
            except Exception:
                out["error"] = "PDF text could not be extracted"
            return out
        r.encoding = r.encoding or "utf-8"
        out["text"] = r.text[:3_000_000]
        if r.status_code in (401, 402, 403, 406, 429, 503) or (r.status_code == 200 and len(out["text"]) < 20000 and BOT_WALL.search(out["text"])):
            out["blocked"] = True
        elif r.status_code >= 400:
            out["error"] = f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        out["error"] = "Timed out after 30 s"
    except requests.exceptions.SSLError:
        out["error"] = "TLS/certificate problem"
    except requests.exceptions.ConnectionError as e:
        out["error"] = "Could not connect (" + clean_text(str(e), 80) + ")"
    except requests.RequestException as e:
        out["error"] = clean_text(str(e), 120)
    return out


def looks_like_feed(res):
    ct = res["content_type"]
    head = res["text"][:400].lstrip().lower()
    return ("xml" in ct and "html" not in ct) or head.startswith("<?xml") or "<rss" in head or "<feed" in head


# ----------------------------------------------------------------------------
# parsing
# ----------------------------------------------------------------------------
def split_title(title):
    """'Assistant Professor - Some University' -> (title, institution) when obvious."""
    # Some RSS feeds prefix the institution (e.g., "Virginia Tech: Assistant Professor").
    if ": " in title:
        org, role = title.split(": ", 1)
        if 3 < len(org) < 90 and re.search(r"\b(?:assistant|associate|full|visiting|clinical|professor|postdoc|lecturer|faculty|instructor)\b", role, re.I):
            return role.strip(), org.strip()
    for sep in (" - ", " – ", " — ", " | ", " at "):
        if sep in title:
            a, b = title.rsplit(sep, 1)
            if INSTITUTION_HINT.search(b) and len(b) < 90:
                return a.strip(), b.strip()
            if INSTITUTION_HINT.search(a) and len(a) < 90 and not INSTITUTION_HINT.search(b):
                return b.strip(), a.strip()
    return title.strip(), ""


def parse_feed(text, page_url):
    parsed = feedparser.parse(text)
    posts = []
    for e in parsed.entries:
        link = e.get("link") or ""
        if not link:
            continue
        title, inst = split_title(clean_text(e.get("title", "")))
        summary = BeautifulSoup(e.get("summary", "") or e.get("description", "") or "", "html.parser").get_text(" ")
        summary = clean_text(summary, 400)
        author = clean_text(e.get("author", ""))
        if not inst and author and INSTITUTION_HINT.search(author):
            inst = author
        if not inst:
            m = re.search(r"(?:Employer|Institution|Organization|Company)\s*:\s*([^.|;\n]{3,90})", summary)
            if m:
                inst = clean_text(m.group(1))
        published = ""
        if e.get("published_parsed"):
            published = time.strftime("%Y-%m-%d", e.published_parsed)
        posts.append({"title": title, "institution": inst, "location": "", "url": urllib.parse.urljoin(page_url, link), "deadline": "", "snippet": summary, "published": published})
    return posts, clean_text(parsed.feed.get("title", "")) if parsed.feed else ""


def parse_jsonld(soup, page_url):
    posts = []
    for tag in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for it in list(items):
            if isinstance(it, dict) and "@graph" in it:
                items.extend(it["@graph"])
        for it in items:
            if not isinstance(it, dict):
                continue
            t = it.get("@type")
            if t == "ItemList":
                for el in it.get("itemListElement", []):
                    if isinstance(el, dict):
                        inner = el.get("item", el)
                        if isinstance(inner, dict) and inner.get("url"):
                            posts.append({"title": clean_text(inner.get("name", "")), "institution": "", "location": "", "url": urllib.parse.urljoin(page_url, inner["url"]), "deadline": "", "snippet": ""})
            elif t == "JobPosting":
                org = it.get("hiringOrganization") or {}
                loc = it.get("jobLocation") or {}
                if isinstance(loc, list):
                    loc = loc[0] if loc else {}
                addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
                location = ", ".join([x for x in [addr.get("addressLocality"), addr.get("addressRegion")] if x]) if isinstance(addr, dict) else ""
                posts.append({
                    "title": clean_text(it.get("title", "")),
                    "institution": clean_text(org.get("name", "")) if isinstance(org, dict) else "",
                    "location": location,
                    "url": urllib.parse.urljoin(page_url, it.get("url") or page_url),
                    "deadline": (it.get("validThrough") or "")[:10],
                    "snippet": clean_text(BeautifulSoup(it.get("description", "") or "", "html.parser").get_text(" "), 400),
                })
    return posts


def card_context(a):
    """Institution and location guessed from the listing card around a link."""
    node = a
    for _ in range(5):
        node = node.parent
        if node is None or node.name in ("body", "html"):
            return "", ""
        if node.name in ("li", "article", "tr") or (node.name == "div" and re.search(r"(job|result|listing|card|item|row|vacancy|posting)", " ".join(node.get("class", [])), re.I)):
            break
    if node is None:
        return "", ""
    title = clean_text(a.get_text(" "))
    lines = [clean_text(s) for s in node.stripped_strings]
    lines = [l for l in lines if l and l != title and len(l) < 120 and l.lower() not in GENERIC_ANCHOR]
    inst, loc = "", ""
    for l in lines:
        if not inst and INSTITUTION_HINT.search(l) and not DATE_LIKE.search(l):
            inst = l
        elif not loc and LOCATION_HINT.search(l) and not INSTITUTION_HINT.search(l) and len(l) < 60:
            loc = l
    if not inst:
        for l in lines:
            if not DATE_LIKE.search(l) and not LOCATION_HINT.search(l) and 3 < len(l) < 80 and not l.endswith(":"):
                inst = l
                break
    return inst, loc


def parse_html_links(soup, page_url, selector=None):
    posts, seen = [], set()
    base_norm = normalize_url(page_url)
    anchors = soup.select(selector) if selector else soup.find_all("a", href=True)
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        url = urllib.parse.urljoin(page_url, href.strip())
        if not url.startswith("http"):
            continue
        n = normalize_url(url)
        if n == base_norm or n in seen:
            continue
        text = clean_text(a.get_text(" ")) or clean_text(a.get("title", "")) or clean_text(a.get("aria-label", ""))
        path_q = urllib.parse.urlsplit(url).path + "?" + urllib.parse.urlsplit(url).query
        if not selector:
            if not JOB_PATH.search(path_q) or NOT_A_POSTING.search(url):
                continue
            if len(text) < 8 or text.lower() in GENERIC_ANCHOR:
                continue
        seen.add(n)
        inst, loc = card_context(a)
        title, inst2 = split_title(text)
        posts.append({"title": title, "institution": inst or inst2, "location": loc, "url": url, "deadline": "", "snippet": ""})
    return posts


def parse_wiki(soup, page_url):
    posts = []
    for h in soup.select("h2, h3, h4"):
        text = clean_text(h.get_text(" ").replace("[edit]", "").replace("[]", ""))
        if not text or len(text) < 8 or not INSTITUTION_HINT.search(text):
            continue
        anchor = h.get("id") or (h.find(attrs={"id": True}) or {}).get("id") or ""
        posts.append({"title": text, "institution": text.split(" - ")[0].split(" (")[0].strip(), "location": "", "url": page_url + ("#" + anchor if anchor else ""), "deadline": "", "snippet": ""})
    return posts


# --- MediaWiki pages (Academic Jobs Wiki) via the wiki's own API -------------
WIKI_HEADING = re.compile(r"^\s*(={2,5})\s*(.*?)\s*\1\s*$")
MONTHS_RX = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
MONTH_NUM = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}


def wiki_page_from_url(url):
    """(api_base, page_title) for a /wiki/Title page or an api.php?...page=Title URL; None if not a wiki URL."""
    p = urllib.parse.urlsplit(url)
    origin = f"{p.scheme}://{p.netloc}"
    if p.path.endswith("/api.php"):
        q = dict(urllib.parse.parse_qsl(p.query))
        if q.get("page"):
            return origin + p.path, urllib.parse.unquote(q["page"]).replace("_", " ")
    m = re.match(r"^/(?:wiki|w)/([^?#]+)", p.path)
    if m:
        return origin + "/api.php", urllib.parse.unquote(m.group(1)).replace("_", " ")
    return None


def strip_wiki_markup(s):
    s = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", s, flags=re.S)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)                # [[link|text]] -> text
    s = re.sub(r"\[(https?://[^\s\]]+)\s+([^\]]+)\]", r"\2 (\1)", s)       # [url label] -> label (url)
    s = re.sub(r"\[(https?://[^\s\]]+)\]", r"\1", s)
    s = re.sub(r"'{2,5}", "", s)
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return clean_text(s)


def wiki_date(text, cycle_year):
    """'Oct. 15' / 'October 15, 2026' / '10/15' -> YYYY-MM-DD, assuming the hiring cycle's year when none is given."""
    m = re.search(MONTHS_RX + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?(?:\s+(\d{4}))?", text, re.I)
    if m:
        mon = MONTH_NUM[m.group(1).lower()[:4] if m.group(1).lower().startswith("sept") else m.group(1).lower()[:3]]
        year = int(m.group(3)) if m.group(3) else (cycle_year if mon >= 7 else cycle_year + 1)
        return f"{year}-{mon:02d}-{int(m.group(2)):02d}"
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
    if m:
        mon, day = int(m.group(1)), int(m.group(2))
        if 1 <= mon <= 12 and 1 <= day <= 31:
            year = int(m.group(3)) if m.group(3) else (cycle_year if mon >= 7 else cycle_year + 1)
            year = year + 2000 if year < 100 else year
            return f"{year}-{mon:02d}-{day:02d}"
    return ""



def wiki_title_metadata(title, cycle_year):
    """Separate hiring-cycle dates and recruiting updates from job identity.

    Wiki editors sometimes append "ZOOM INTERVIEW INVITATIONS SENT OUT" to the
    heading, which must not become a new posting.
    """
    cleaned = (title or "").strip()
    notices = []
    date = ""
    # Only isolate recognizable process announcements, not academic specialties.
    suffix = re.search(
        r"\s+((?:(?:ZOOM|PHONE|VIRTUAL|ON.CAMPUS|CAMPUS)\s+)?"
        r"INTERVIEW(?:S)?\s+(?:INVITATIONS?|INVITES?|REQUESTS?)\s+[A-Z \-/]+"
        r"|OFFERS?\s+(?:MADE|EXTENDED|ACCEPTED)"
        r"|SEARCH\s+(?:CLOSED|CANCELLED)|POSITION\s+FILLED)\s*$",
        cleaned)
    if suffix:
        notices.append(suffix.group(1).strip())
        cleaned = cleaned[:suffix.start()].strip()
    date_marker = re.search(
        r"\s*\(\s*(?:application\s+)?(?:deadline|review begins|priority review)\s*:\s*"
        r"([^)]+)\)", cleaned, re.I)
    if date_marker:
        date = wiki_date(date_marker.group(1),cycle_year)
        cleaned=(cleaned[:date_marker.start()]+cleaned[date_marker.end():]).strip()
    return cleaned, date, notices


def specific_wiki_job_url(url):
    """Require a position-specific official link; never deduplicate generic HR pages."""
    if not url:
        return ""
    p=urllib.parse.urlsplit(url)
    path=p.path.lower().rstrip("/")
    valid=bool(re.search(r"/(?:career|jobs?|positions?|postings?|requisitions?|vacancies)/"
                         r"(?:[a-z0-9_-]*\d{3,}[a-z0-9_-]*|[a-z0-9_-]{12,})$",path))
    params=dict(urllib.parse.parse_qsl(p.query))
    valid=valid or any(k.lower() in ("jobid","job_id","requisition","postingid","reqid")
                       and re.search(r"\d{4,}",v) for k,v in params.items())
    return normalize_url(url) if valid else ""


def collapse_wiki_duplicates(jobs):
    """Consolidate renamed wiki headings without changing the oldest feed ID.

    Preserve firstSeen and the tracked old ID, keep lastSeen/current wiki link,
    combine notes, and avoid merging different official requisitions or boards.
    """
    by_ad={}
    removed=0
    candidates=sorted(
        [j for j in jobs.values() if j.get("sourceId")=="academic-jobs-wiki"],
        key=lambda j:(j.get("firstSeen") or "",j.get("id") or ""))
    for j in candidates:
        base_year=2026
        m=re.search(r"20\d{2}-20\d{2}",j.get("url",""))
        if m:base_year=int(m.group()[:4])
        title, date, notices=wiki_title_metadata(j.get("title",""),base_year)
        j["title"]=title
        if date and not j.get("deadline"):j["deadline"]=date
        current_notes=j.get("statuses") or []
        for note in notices:
            if note not in current_notes:current_notes.append(note)
        j["statuses"]=current_notes
        ad=specific_wiki_job_url(j.get("adUrl",""))
        if not ad:continue
        # One official requisition plus one source family is sufficient proof.
        existing=by_ad.get(ad)
        if not existing:
            by_ad[ad]=j
            continue
        # Conflicting explicit job numbers mean this is not safely one position.
        a=existing.get("jobNumber");b=j.get("jobNumber")
        if a and b and a!=b:continue
        # Preserve the older ID so imported Jobs entries do not lose their link.
        newer=j if (j.get("lastSeen") or "") >= (existing.get("lastSeen") or "") else existing
        for k in ("lastSeen","url","adUrl"):
            if newer.get(k):existing[k]=newer[k]
        for k in ("deadline","deadlineKind","deadlineEvidence","detailText",
                  "applicationEvidence","applicationCoverage","verifiedApplicationUrl","jobNumber"):
            if not existing.get(k) and j.get(k):existing[k]=j[k]
        prior_notes=list(existing.get("statuses") or [])
        combined=list(dict.fromkeys(prior_notes+(j.get("statuses") or [])))
        existing["statuses"]=combined
        new_notes=[note for note in combined if note not in prior_notes]
        if new_notes:
            existing["changedAt"]=max(existing.get("changedAt") or "",j.get("changedAt") or "",
                                      j.get("firstSeen") or "")
            existing["newStatuses"]=list(dict.fromkeys((existing.get("newStatuses") or [])+
                                                    new_notes))[-6:]
        existing["alternateFeedIds"]=list(dict.fromkeys(
            (existing.get("alternateFeedIds") or [])+(j.get("alternateFeedIds") or [])+[j["id"]]))
        jobs.pop(j["id"],None)
        removed+=1
    return removed


def parse_wikitext(wikitext, page_url, page_title):
    """Each institution heading becomes a posting; its bullet lines become status updates."""
    cy = re.search(r"(20\d\d)", page_title)
    cycle_year = int(cy.group(1)) if cy else dt.datetime.now().year
    posts, section, current = [], "", None

    def close():
        if current and current["title"]:
            body = current["body"]
            statuses = [strip_wiki_markup(l.lstrip("*#: ").strip()) for l in body if re.match(r"^\s*[*#:]+", l)]
            statuses = [x for x in statuses if x][-15:]
            prose = " ".join(strip_wiki_markup(l) for l in body if not re.match(r"^\s*[*#:]+", l) and l.strip())
            heading = current["title"]
            inst, position, location = heading, "", ""
            m = re.match(r"^(.*?)\s*\(([A-Z]{2}|[A-Za-z .]+)\)\s*[-–—:]\s*(.+)$", heading)
            if m:
                inst, location, position = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            else:
                m = re.match(r"^(.*?)\s*[-–—:]\s+(.+)$", heading)
                if m:
                    inst, position = m.group(1).strip(), m.group(2).strip()
                m2 = re.match(r"^(.*?)\s*\(([A-Z]{2}|[A-Za-z .]+)\)\s*$", inst)
                if m2:
                    inst, location = m2.group(1).strip(), m2.group(2).strip()
            position, heading_deadline, heading_updates = wiki_title_metadata(position or heading,cycle_year)
            statuses = list(dict.fromkeys(statuses + heading_updates))
            deadline = heading_deadline
            for line in statuses + [prose]:
                if re.search(r"deadline|due|review (?:of applications )?begins|apply by|closes", line, re.I):
                    deadline = wiki_date(line, cycle_year)
                    if deadline:
                        break
            urlm = re.search(r"https?://[^\s\]\)]+", " ".join(body))
            anchor = heading.replace(" ", "_")
            posts.append({
                "title": position or heading, "institution": inst, "location": location,
                "url": page_url.split("#")[0] + "#" + anchor, "deadline": deadline,
                "snippet": clean_text(prose, 400), "statuses": statuses, "section": section,
                "adUrl": urlm.group(0).rstrip(".,;") if urlm else "",
            })

    for line in wikitext.split("\n"):
        h = WIKI_HEADING.match(line)
        if h:
            level, text = len(h.group(1)), strip_wiki_markup(h.group(2))
            is_entry = bool(INSTITUTION_HINT.search(text) or re.search(r"\s[-–—]\s", text))
            if is_entry and level >= 2 and not re.search(r"^(recent activity|see also|full[- ]time|tenure|visiting|postdoc|word on the street|discussion|links|general|instructions|notes)", text, re.I):
                close()
                current = {"title": text, "body": []}
            else:
                close()
                current = None
                section = text
            continue
        if current is not None:
            current["body"].append(line)
    close()
    return posts


def collect_wiki(url):
    """Read a MediaWiki page through api.php (the sanctioned machine interface)."""
    info = wiki_page_from_url(url)
    result = {"url": url, "status": "error", "httpStatus": None, "kind": "wiki", "title": "", "error": None}
    if not info:
        result["error"] = "Not a wiki page URL"
        return result, []
    api, title = info
    api_url = api + "?" + urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext", "format": "json", "formatversion": "2"})
    if not robots_allowed(api_url):
        result["status"] = "robots"
        return result, []
    res = fetch(api_url)
    result["httpStatus"] = res["status"]
    if res["blocked"]:
        result["status"] = "blocked"
        return result, []
    if res["error"]:
        result["error"] = res["error"]
        return result, []
    try:
        data = json.loads(res["text"])
    except json.JSONDecodeError:
        result["error"] = "The wiki API did not return JSON"
        return result, []
    if "error" in data:
        result["error"] = clean_text(str(data["error"].get("info") or data["error"]), 160)
        return result, []
    parse = data.get("parse") or {}
    wikitext = parse.get("wikitext")
    if isinstance(wikitext, dict):
        wikitext = wikitext.get("*", "")
    result["title"] = clean_text(parse.get("title") or title, 120)
    page_url = api.rsplit("/api.php", 1)[0] + "/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    posts = parse_wikitext(wikitext or "", page_url, title)
    result["status"] = "ok" if posts else "no_postings"
    return result, posts


# --- JSON job boards (Web Scribble and similar) --------------------------------
MAX_JSON_PAGES = 6


def _first(d, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, dict):
            v = v.get("name") or v.get("title") or v.get("label") or ""
        if v not in (None, "", [], {}):
            return v
    return ""


def parse_json_jobs(data, page_url):
    """Find the list of job objects in a JSON reply and normalise the common field names."""
    items = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("data", "jobs", "results", "items", "hits", "postings", "records"):
            v = data.get(key)
            if isinstance(v, list):
                items = v
                break
            if isinstance(v, dict) and isinstance(v.get("data"), list):
                items = v["data"]
                break
    posts = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        title = clean_text(str(_first(it, "title", "job_title", "name", "position", "headline")))
        url = _first(it, "url", "link", "job_url", "detail_url", "href", "apply_url")
        if not title:
            continue
        if not url and it.get("id"):
            url = urllib.parse.urljoin(page_url, f"/job/{it['id']}")
        url = urllib.parse.urljoin(page_url, str(url))
        loc = it.get("location") or it.get("city") or ""
        if isinstance(loc, dict):
            loc = ", ".join(str(x) for x in [loc.get("city"), loc.get("state") or loc.get("region"), loc.get("country")] if x)
        snippet = _first(it, "shortDescription", "short_description", "summary", "description", "excerpt")
        snippet = clean_text(BeautifulSoup(str(snippet), "html.parser").get_text(" "), 400) if snippet else ""
        posted = str(_first(it, "posted_date", "date_posted", "posted", "date", "created_at", "published"))[:10]
        deadline = str(_first(it, "deadline", "application_deadline", "closing_date", "expires", "expiration_date", "valid_through"))[:10]
        posts.append({"title": title, "institution": clean_text(str(_first(it, "company", "employer", "organization", "institution", "company_name", "hiringOrganization"))),
                      "location": clean_text(str(loc)), "url": url, "deadline": deadline if re.match(r"^\d{4}-\d{2}-\d{2}$", deadline) else "",
                      "snippet": snippet, "published": posted if re.match(r"^\d{4}-\d{2}-\d{2}$", posted) else ""})
    nxt = None
    if isinstance(data, dict):
        links, meta = data.get("links") or {}, data.get("meta") or {}
        if isinstance(links, dict) and links.get("next"):
            nxt = urllib.parse.urljoin(page_url, str(links["next"]))
        elif isinstance(meta, dict) and meta.get("current_page") and meta.get("last_page") and int(meta["current_page"]) < int(meta["last_page"]):
            p = urllib.parse.urlsplit(page_url)
            q = dict(urllib.parse.parse_qsl(p.query))
            q["page"] = str(int(meta["current_page"]) + 1)
            nxt = urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ""))
    return posts, nxt


def looks_like_json(res):
    return "json" in res["content_type"] or res["text"][:200].lstrip().startswith(("{", "["))


def collect_json(url, pages=MAX_JSON_PAGES):
    result = {"url": url, "status": "error", "httpStatus": None, "kind": "json", "title": "", "error": None}
    if not robots_allowed(url):
        result["status"] = "robots"
        return result, []
    posts, page_url, count = [], url, 0
    while page_url and count < pages:
        res = fetch(page_url)
        count += 1
        if count == 1:
            result["httpStatus"] = res["status"]
        if res["blocked"]:
            if count == 1:
                result["status"] = "blocked"
                return result, []
            break
        if res["error"] or not looks_like_json(res):
            if count == 1:
                result["error"] = res["error"] or "Not a JSON reply"
                return result, []
            break
        try:
            data = json.loads(res["text"])
        except json.JSONDecodeError:
            result["error"] = "Malformed JSON"
            return result, []
        found, nxt = parse_json_jobs(data, page_url)
        posts.extend(found)
        if not found or not nxt or normalize_url(nxt) == normalize_url(page_url):
            break
        page_url = nxt
        time.sleep(PAUSE_BETWEEN_REQUESTS)
    result["title"] = urllib.parse.urlsplit(url).netloc
    result["status"] = "ok" if posts else "no_postings"
    return result, posts


def find_next_link(soup, page_url):
    link = soup.find("link", rel=lambda v: v and "next" in v)
    if link and link.get("href"):
        return urllib.parse.urljoin(page_url, link["href"])
    for a in soup.find_all("a", href=True):
        rel = " ".join(a.get("rel", [])) if isinstance(a.get("rel"), list) else (a.get("rel") or "")
        label = clean_text(a.get_text(" ")).lower()
        if "next" in rel.lower() or label in ("next", "next »", "next ›", "›", "»", "next page") or "next" in (a.get("aria-label") or "").lower():
            return urllib.parse.urljoin(page_url, a["href"])
    return None


def collect_source(url, kind="auto", selector=None, pages=MAX_PAGES):
    """Fetch one source and return (result, postings)."""
    if kind == "wiki" or (kind == "auto" and wiki_page_from_url(url) and ("fandom.com" in url or "/wiki/" in url or "api.php" in url)):
        return collect_wiki(url)
    if kind == "json" or re.search(r"/api/v\d+/jobs|\.json(\?|$)", url):
        return collect_json(url)
    result = {"url": url, "status": "error", "httpStatus": None, "kind": kind, "title": "", "error": None}
    if not robots_allowed(url):
        result["status"] = "robots"
        return result, []
    posts, page_url, page_count = [], url, 0
    while page_url and page_count < max(1, pages):
        res = fetch(page_url)
        page_count += 1
        if page_count == 1:
            result["httpStatus"] = res["status"]
        if res["blocked"]:
            if page_count == 1:
                result["status"] = "blocked"
                return result, []
            break
        if res["error"]:
            if page_count == 1:
                result["error"] = res["error"]
                return result, []
            break
        if kind in ("auto", "rss") and (kind == "rss" or looks_like_feed(res)):
            result["kind"] = "rss"
            found, ftitle = parse_feed(res["text"], page_url)
            result["title"] = result["title"] or ftitle
            posts.extend(found)
            break
        if kind in ("auto", "html") and looks_like_json(res):
            return collect_json(page_url)
        soup = BeautifulSoup(res["text"], "html.parser")
        if page_count == 1:
            result["title"] = clean_text(soup.title.get_text() if soup.title else "", 120)
        if kind == "wiki":
            result["kind"] = "wiki"
            posts.extend(parse_wiki(soup, page_url))
            break
        result["kind"] = "html"
        found = parse_jsonld(soup, page_url)
        found += parse_html_links(soup, page_url, selector)
        if not found and page_count == 1 and re.search(r"web ?scribble", res["text"], re.I):
            # Web Scribble boards draw the list with JavaScript but publish the same data at /api/v1/jobs.
            p = urllib.parse.urlsplit(page_url)
            api_result, api_posts = collect_json(f"{p.scheme}://{p.netloc}/api/v1/jobs")
            if api_posts:
                api_result["title"] = result["title"] or api_result["title"]
                api_result["url"] = url
                api_result["kind"] = "json"
                return api_result, api_posts
        posts.extend(found)
        nxt = find_next_link(soup, page_url)
        if not found or not nxt or normalize_url(nxt) == normalize_url(page_url):
            break
        page_url = nxt
        time.sleep(PAUSE_BETWEEN_REQUESTS)
    # de-duplicate by normalized url
    uniq, seen = [], set()
    for p in posts:
        n = normalize_url(p["url"])
        if n in seen or not p.get("title"):
            continue
        seen.add(n)
        uniq.append(p)
    result["status"] = "ok" if uniq else "no_postings"
    return result, uniq


# ----------------------------------------------------------------------------
# fit scoring against data/profile.json
# ----------------------------------------------------------------------------
def load_profile():
    """Profile = three term lists with weights. Missing file -> no scoring."""
    p = load_json(PROFILE_PATH, {})
    weights = p.get("weights") or {}
    tiers = [("core", int(weights.get("core", 3))), ("related", int(weights.get("related", 1))), ("avoid", int(weights.get("avoid", -3)))]
    terms = []
    for tier, w in tiers:
        for t in p.get(tier) or []:
            t = clean_text(str(t)).lower()
            if t and w:
                terms.append((t, w, tier, re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?:s|es)?(?![a-z0-9])", re.I)))
    return {"terms": terms, "updatedAt": p.get("updatedAt") or "", "goodFit": int(p.get("goodFit", 4))}


def score_text(text, profile):
    """Sum the weight of every profile term present in text; each term counts once."""
    score, matched = 0, []
    for term, w, tier, rx in profile["terms"]:
        if rx.search(text):
            score += w
            matched.append(term if tier != "avoid" else "-" + term)
    return score, matched


ROLE_ONLY_TERMS = {
    "assistant professor", "tenure-track", "tenure track",
    "associate professor", "open rank", "full professor",
}


def rank_posting(job, profile, page_text=""):
    """Prioritize disciplinary relevance rather than generic academic rank.

    Role words establish eligibility but are not evidence of research fit.
    Positives from lengthy descriptions are capped to limit boilerplate.
    """
    headline = " ".join(str(job.get(k) or "") for k in ("title", "institution", "section"))
    details = " ".join([str(job.get("snippet") or ""), " ".join(job.get("statuses") or []), page_text])
    weights = {("-" + term if tier == "avoid" else term): weight
               for term, weight, tier, _ in profile["terms"]}
    def domain_evidence(terms):
        return [term for term in terms if term.lstrip("-") not in ROLE_ONLY_TERMS]

    title_score, title_terms = score_text(headline, profile)
    detail_score, detail_terms = score_text(details[:12000], profile)
    title_terms = domain_evidence(title_terms)
    detail_terms = domain_evidence(detail_terms)
    headline_score = sum(weights.get(t, 0) for t in title_terms)
    title_set = set(title_terms)
    extra = [term for term in detail_terms if term not in title_set]
    positive = min(6, sum(max(0, weights.get(t, 0)) for t in extra))
    negative = max(-18, sum(min(0, weights.get(t, 0)) for t in extra))
    score=max(-35, headline_score * 2 + positive + negative)
    # Communication job boards include many nonacademic communication-adjacent
    # positions. Do not present an engineering/business vacancy as a faculty match.
    title=(job.get("title") or "").lower()
    academic=bool(re.search(r"\b(?:professor|professorship|faculty|postdoc(?:toral)?|lecturer|"
                            r"instructor|research fellow|tenure.track|research scientist)\b",title))
    if not academic:
        score=min(0, score)
    return score, title_terms + extra


def compact_posting_details(page_text):
    """Keep a useful opening PLUS application instructions near the end."""
    if len(page_text) <= STORED_DETAIL_CAP:
        return page_text
    lead = page_text[:4200].rstrip()
    tail = page_text[4200:]
    triggers = list(re.finditer(
        r"\b(?:application materials|application instructions|to apply|how to apply|"
        r"required documents|please submit|submit the following|review of applications)\b",
        tail, flags=re.I))
    if triggers:
        # Later mentions of 'how to apply' are more useful than unrelated page boilerplate.
        section = tail[max(0, triggers[-1].start() - 130):]
        return (lead + "\n[Application instructions later in posting]\n" +
                section[:STORED_DETAIL_CAP - len(lead) - 49])
    return page_text[:STORED_DETAIL_CAP]


def extract_main_text(html):
    """The readable part of a posting page: main/article/job-description if present, else body."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "iframe"]):
        tag.decompose()
    node = soup.find("main") or soup.find("article")
    if node is None:
        for el in soup.find_all(["div", "section"], attrs={"class": True}):
            cls = " ".join(el.get("class", [])).lower()
            if re.search(r"(job-?desc|job-?detail|job-?content|description|posting|vacancy|main-content)", cls):
                node = el
                break
    node = node or soup.body or soup
    # Preserve paragraph and list boundaries for the downstream application
    # materials parser. Flattening everything to one line lost the actual checklist.
    for element in node.select("p,li,h1,h2,h3,h4,br"):
        element.insert_before("\n")
    chunks = [clean_text(part) for part in node.get_text(" ", strip=True).split("\n")]
    return "\n".join(part for part in chunks if part)[:DETAIL_TEXT_CAP]


def posting_text(job, page_text=""):
    return " ".join([job.get("title", ""), job.get("institution", ""), job.get("location", ""), job.get("snippet", ""), " ".join(job.get("statuses") or []), job.get("section", ""), page_text])


def _source_lines(response):
    if "pdf" in response["content_type"]:
        return [line.strip() for line in response["text"].splitlines() if line.strip()]
    return text_lines(response["text"])


def _source_text(response):
    if "pdf" in response["content_type"]:
        return response["text"][:DETAIL_TEXT_CAP]
    return extract_main_text(response["text"])


def _same_posting(job, text):
    """Verify links before attributing their deadlines or requirements to a job."""
    t = text.lower()
    num = job.get("jobNumber") or job_number(job.get("adUrl") or job.get("url", ""))
    if num and re.search(r"\b" + re.escape(str(num)) + r"\b", text):
        return True
    stop = {"assistant", "associate", "full", "visiting", "clinical", "professor",
            "professorship", "university", "department", "college", "school",
            "position", "faculty", "tenure", "track", "open", "rank"}
    words = {w.lower() for w in re.findall(r"[a-z]{5,}", job.get("title", ""), re.I)} - stop
    if words and sum(w in t for w in words) >= min(2, len(words)):
        return True
    # Generic wiki titles may not name a specialty; corroborate the institution.
    inst = {w.lower() for w in re.findall(r"[a-z]{5,}", job.get("institution", ""), re.I)} - stop - {"state"}
    return bool(not words and inst and sum(w in t for w in inst) >= min(2, len(inst)))


def _structured_deadline(html, url, job):
    if not html or "pdf" in (html[:12].lower()):
        return []
    # Job-board validThrough describes expiration of the syndicated advertisement,
    # not necessarily the university's application closing date.
    visible=BeautifulSoup(html,"html.parser").get_text(" ",strip=True)
    if re.search(r"(?:Apply By:|applications? (?:accepted|reviewed))\s*(?:Open until filled|until (?:the )?position is filled)",visible,re.I):
        return []
    try:
        candidates = parse_jsonld(BeautifulSoup(html, "html.parser"), url)
        matching = [x for x in candidates if x.get("deadline") and
                    (x.get("title") or "").lower() in (job.get("title") or "").lower()]
        return [{"date": x["deadline"], "type": "closing", "url": url,
                 "evidence": "Official JobPosting metadata (validThrough): " + x["deadline"],
                 "source": "structured-data"} for x in matching
                if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", x["deadline"])]
    except (TypeError, ValueError, AttributeError):
        return []


def apply_scores(jobs, profile, today):
    """Fetch full calls, follow verified application links and preserve provenance."""
    if not profile["terms"]:
        for j in jobs.values():
            for k in ("score", "matched", "scoredOn", "scoredAt", "scoredFor"): j.pop(k, None)
        return 0
    stale = lambda j: j.get("scoredFor") != profile["updatedAt"] or "score" not in j or j.get("scoredVersion") != FIT_VERSION
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=RESCORE_WINDOW_DAYS)).isoformat()
    candidates = [j for j in jobs.values()
                  if (stale(j) or j.get("scoredOn") != "page" or not j.get("detailText")
                      or not j.get("applicationEvidence") or j.get("applicationCoverage") != "deadline_and_materials")
                  and (j.get("firstSeen") or "") >= cutoff
                  and (j.get("adUrl") or j.get("url") or "").startswith("http")
                  and int(j.get("detailTries", 0)) < MAX_DETAIL_TRIES
                  and (j.get("adUrl") or "statuses" not in j)]
    # Newly found postings go first, but old incomplete jobs remain eligible for backfill.
    candidates.sort(key=lambda j: j.get("firstSeen") or "", reverse=True)
    host_failures, fetched, deep_budget = {}, 0, 45
    for j in candidates[:MAX_DETAIL_FETCHES]:
        target = j.get("adUrl") or j["url"]
        host = urllib.parse.urlsplit(target).netloc
        if host_failures.get(host, 0) >= MAX_HOST_FAILURES or not robots_allowed(target):
            continue
        res = fetch(target)
        j["detailTries"] = int(j.get("detailTries", 0)) + 1
        fetched += 1
        time.sleep(PAUSE_BETWEEN_REQUESTS)
        if res["blocked"] or res["error"] or not res["text"]:
            host_failures[host] = host_failures.get(host, 0) + 1
            j["applicationFetchStatus"] = "blocked" if res["blocked"] else "unavailable"
            continue
        page_text = _source_text(res)
        # Wiki body links are only leads. Do not attribute another university's call.
        if j.get("adUrl") and not _same_posting(j, page_text):
            j["verificationWarnings"] = ["The linked advertisement could not be matched to this position; verify the URL."]
            j["applicationFetchStatus"] = "link_mismatch"
            continue
        evidence = evidence_from_lines(_source_lines(res), res["final_url"], "linked-call" if j.get("adUrl") else "job-board")
        if "pdf" not in res["content_type"]:
            evidence["deadlineEvidence"].extend(_structured_deadline(res["text"], res["final_url"], j))
        j["applicationEvidence"] = evidence
        j["applicationCoverage"] = describe_coverage(evidence)
        j["applicationFetchStatus"] = "read"
        if j.get("adUrl"):
            j["verifiedApplicationUrl"] = res["final_url"]
            j["applicationSource"] = "linked_job_call"
        links = application_links(res["text"], res["final_url"]) if "pdf" not in res["content_type"] else []
        j["applicationLinkCandidates"] = links
        seen = {normalize_url(res["final_url"])}
        queue = [(x, 1) for x in links]
        traversed = 0
        while queue and deep_budget > 0 and traversed < 4:
            link, depth = queue.pop(0)
            dest = link["url"]
            normalized = normalize_url(dest)
            if normalized in seen:
                continue
            seen.add(normalized)
            if not robots_allowed(dest):
                continue
            deep_budget -= 1
            traversed += 1
            time.sleep(PAUSE_BETWEEN_REQUESTS)
            deep = fetch(dest)
            if deep["error"] or deep["blocked"] or not deep["text"]:
                continue
            deep_text = _source_text(deep)
            if not _same_posting(j, deep_text):
                continue
            more = evidence_from_lines(_source_lines(deep), deep["final_url"], "official-job-call")
            if "pdf" not in deep["content_type"]:
                more["deadlineEvidence"].extend(_structured_deadline(deep["text"], deep["final_url"], j))
            if more["deadlineEvidence"] or more["materialEvidence"]:
                j["applicationEvidence"] = merge_evidence(j["applicationEvidence"], more)
                j["applicationCoverage"] = describe_coverage(j["applicationEvidence"])
                j["verifiedApplicationUrl"] = deep["final_url"]
                j["applicationSource"] = "verified_linked_page"
                page_text = (page_text + "\n" + deep_text)[:DETAIL_TEXT_CAP]
                if j["applicationCoverage"] == "deadline_and_materials":
                    break
            if depth < 2 and "pdf" not in deep["content_type"]:
                queue.extend((x, depth + 1) for x in application_links(deep["text"], deep["final_url"])[:3])
        chosen = (j.get("applicationEvidence") or {}).get("deadlineEvidence") or []
        if chosen:
            explicit=[x for x in chosen if x.get("source")!="structured-data"]
            source_dates=explicit or chosen
            item = next((x for x in source_dates if x["type"]=="closing"),source_dates[0])
            # Replace prior syndication metadata with the employer's real review date.
            can_update=(not j.get("deadline") or
                        (j.get("deadlineEvidence") or {}).get("source")=="structured-data" or
                        (item["type"]=="priority" and re.search(r"screening|review begins",item.get("evidence",""),re.I)))
            if can_update:
                j["deadline"]=item["date"]
                j["deadlineKind"]=item["type"]
                j["deadlineEvidence"]=item
        if "pdf" not in res["content_type"] and re.search(r"(?:Apply By:|applications? (?:accepted|reviewed))\s*(?:Open until filled|until (?:the )?position is filled)",res["text"],re.I):
            j["deadlineNote"]="Applications remain open until the position is filled; any listed review date is not a final closing date."
        try:
            structured = parse_jsonld(BeautifulSoup(res["text"], "html.parser"), target) if "pdf" not in res["content_type"] else []
            item = next((x for x in structured if x.get("title") and
                         (x["title"].lower() in (j.get("title") or "").lower()
                          or (j.get("title") or "").lower() in x["title"].lower())), None)
            if item:
                for field in ("institution", "location", "deadline"):
                    if item.get(field) and not j.get(field):
                        if field=="deadline" and "open until filled" in page_text.lower():
                            continue  # validThrough is only the board's expiry
                        j[field] = item[field]
                if item.get("snippet") and len(item["snippet"]) > len(j.get("snippet") or ""):
                    j["snippet"] = item["snippet"]
        except (TypeError, ValueError, AttributeError):
            pass
        num = job_number(target, page_text)
        if num:
            j["jobNumber"] = num
        if len(page_text) >= 150:
            j["detailText"] = compact_posting_details(page_text)
            j["detailCollectedAt"] = today
        j["score"], j["matched"] = rank_posting(j, profile, page_text)
        j["scoredOn"], j["scoredAt"], j["scoredFor"] = "page", today, profile["updatedAt"]
        j["scoredVersion"] = FIT_VERSION
        if not j.get("snippet") and page_text:
            j["snippet"] = page_text[:300]
    for j in jobs.values():
        if stale(j):
            j["score"], j["matched"] = rank_posting(j, profile, j.get("detailText", ""))
            j["scoredOn"], j["scoredAt"], j["scoredFor"] = ("page" if j.get("detailText") else "wiki" if "statuses" in j else "title"), today, profile["updatedAt"]
            j["scoredVersion"] = FIT_VERSION
    return fetched

def passes_filters(post, include, exclude):
    hay = " ".join([post.get("title", ""), post.get("institution", ""), post.get("snippet", "")]).lower()
    if include and not any(k.lower() in hay for k in include):
        return False
    if exclude and any(k.lower() in hay for k in exclude):
        return False
    return True


# ----------------------------------------------------------------------------
# commands
# ----------------------------------------------------------------------------

TO_APPLY_OFFICIAL = re.compile(
    r"\bto apply[,:]?\s+(?:please\s+)?(?:visit|at|via)?\s*"
    r"(https?://[^\s<>\)\]\"']+)",re.I)


def official_identity(job):
    """Use an explicit position-specific employer URL across different job boards."""
    urls=[job.get("adUrl") or "",job.get("verifiedApplicationUrl") or ""]
    body=job.get("detailText") or ""
    urls += [m.group(1).rstrip(".,;") for m in TO_APPLY_OFFICIAL.finditer(body)]
    for url in urls:
        official=specific_wiki_job_url(url)
        if official and not re.search(r"(?:^|\.)(?:chronicle\.com|insidehighered\.com|"
                                      r"higheredjobs\.com|indeed\.com)$",
                                      urllib.parse.urlsplit(url).netloc.lower()):
            return official
    return ""


def collapse_cross_source_duplicates(jobs):
    """A university requisition overrides unrelated board posting IDs.

    Exact employer URLs establish identity; approximate titles alone cannot.
    Preserve one stable record with other source links and historical feed IDs.
    """
    seen={}
    removed=0
    postings=sorted(list(jobs.values()),key=lambda j:(j.get("firstSeen") or "",j.get("id") or ""))
    for job in postings:
        key=official_identity(job)
        if not key:continue
        existing=seen.get(key)
        if existing is None:
            seen[key]=job
            continue
        alternate={"id":job["id"],"sourceId":job.get("sourceId",""),"url":job.get("url",""),
                   "title":job.get("title",""),"jobNumber":job.get("jobNumber","")}
        links=list(existing.get("alternateListings") or [])
        if alternate["url"] and not any(x.get("url")==alternate["url"] for x in links):
            links.append(alternate)
        links.extend(x for x in (job.get("alternateListings") or [])
                     if x.get("url") and not any(y.get("url")==x["url"] for y in links))
        existing["alternateListings"]=links
        existing["alternateFeedIds"]=list(dict.fromkeys(
            (existing.get("alternateFeedIds") or [])+
            (job.get("alternateFeedIds") or [])+[job["id"]]))
        if (job.get("lastSeen") or "")>(existing.get("lastSeen") or ""):
            existing["lastSeen"]=job["lastSeen"]
        for field in ("department","location","detailText","applicationLinkCandidates",
                      "applicationCoverage","deadlineNote","jobNumber","matched"):
            if not existing.get(field) and job.get(field):existing[field]=job[field]
        if job.get("detailText") and len(job["detailText"])>len(existing.get("detailText") or ""):
            existing["detailText"]=job["detailText"]
        if job.get("applicationEvidence"):
            existing["applicationEvidence"]=merge_evidence(
                existing.get("applicationEvidence") or {},job["applicationEvidence"])
            existing["applicationCoverage"]=describe_coverage(existing["applicationEvidence"])
        existing["verifiedApplicationUrl"]=key
        existing["score"]=max(existing.get("score") or 0,job.get("score") or 0)
        if not existing.get("statuses") and job.get("statuses"):
            existing["statuses"]=job["statuses"]
        evidence=(existing.get("applicationEvidence") or {}).get("deadlineEvidence") or []
        # Prefer the official review/screening language over a board's metadata
        # validThrough; only treat a genuine closing date as a hard deadline.
        direct=[x for x in evidence if x.get("source")!="structured-data"
                and not re.search(r"(?:date\s+)?posted\s*[:.]|posted\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
                                  x.get("evidence",""),re.I)]
        priority=next((x for x in direct if x.get("type")=="priority"),None)
        closing=next((x for x in direct if x.get("type")=="closing"),None)
        chosen=closing or priority
        if chosen:
            existing["deadline"]=chosen["date"]
            existing["deadlineKind"]=chosen["type"]
            existing["deadlineEvidence"]=chosen
        elif existing.get("deadline") and "open until filled" in (existing.get("detailText") or "").lower():
            existing["deadlineKind"]="priority"
        if existing.get("deadlineKind")=="priority" and "open until filled" in (existing.get("detailText") or "").lower():
            existing["deadlineNote"]="Applications remain open until filled; the stated date is for initial review, not a hard closing."
        jobs.pop(job["id"],None)
        removed+=1
    return removed


def run_all(force=False):
    conf = load_json(SOURCES_PATH, {"sources": []})
    feed = load_json(FEED_PATH, {"schemaVersion": 1, "generatedAt": None, "sources": [], "jobs": []})
    prev_status = {s.get("id"): s for s in feed.get("sources", [])}
    jobs = {j["id"]: j for j in feed.get("jobs", []) if j.get("id")}
    statuses = []
    today = now_iso()

    for src in conf.get("sources", []):
        sid = src.get("id") or job_id(src.get("url", ""))
        st = {"id": sid, "name": src.get("name", sid), "url": src.get("url", ""), "kind": src.get("kind", "auto"), "enabled": src.get("enabled", True) is not False}
        prev = prev_status.get(sid, {})
        if not st["enabled"]:
            st.update({k: prev.get(k) for k in ("status", "httpStatus", "error", "checkedAt", "found", "new")})
            statuses.append(st)
            continue
        if not force and src.get("frequency") == "weekly" and prev.get("checkedAt"):
            try:
                last = dt.datetime.fromisoformat(prev["checkedAt"].replace("Z", "+00:00"))
                if (dt.datetime.now(dt.timezone.utc) - last).days < 6:
                    st.update({k: prev.get(k) for k in ("status", "httpStatus", "error", "checkedAt", "found", "new")})
                    statuses.append(st)
                    print(f"[skip]  {st['name']} (weekly, checked {prev['checkedAt']})")
                    continue
            except ValueError:
                pass
        print(f"[fetch] {st['name']}  {st['url']}")
        result, posts = collect_source(st["url"], src.get("kind", "auto"), src.get("linkSelector"))
        limit = int(src.get("limit") or 60)
        kept = [p for p in posts if passes_filters(p, src.get("include") or [], src.get("exclude") or [])][:limit]
        new = 0
        for p in kept:
            jid = job_id(p["url"])
            rec = jobs.get(jid)
            if rec is None:
                new += 1
                rec = {"id": jid, "sourceId": sid, "firstSeen": today}
                jobs[jid] = rec
            rec.update({"title": p["title"], "institution": p.get("institution", "") or rec.get("institution", ""), "location": p.get("location", "") or rec.get("location", ""), "url": p["url"], "deadline": p.get("deadline", "") or rec.get("deadline", ""), "snippet": p.get("snippet", "") or rec.get("snippet", ""), "lastSeen": today})
            if not rec.get("jobNumber"):
                num = job_number(p["url"], (p.get("title", "") + " " + p.get("snippet", "")))
                if num:
                    rec["jobNumber"] = num
            if p.get("published"):
                rec["published"] = p["published"]
            if "statuses" in p:  # wiki entry: keep the status lines and note what changed since last time
                old_statuses = rec.get("statuses") or []
                added = [x for x in p["statuses"] if x not in old_statuses]
                if added and old_statuses:
                    rec["changedAt"], rec["newStatuses"] = today, added[-6:]
                elif not old_statuses:
                    rec.setdefault("changedAt", rec["firstSeen"])
                rec["statuses"], rec["section"] = p["statuses"], p.get("section", "")
                if p.get("adUrl"):
                    rec["adUrl"] = p["adUrl"]
        st.update({"status": result["status"], "httpStatus": result["httpStatus"], "error": result["error"], "checkedAt": today, "found": len(kept), "new": new, "kind": result["kind"]})
        statuses.append(st)
        print(f"        -> {result['status']} (http {result['httpStatus']}), {len(posts)} parsed, {len(kept)} kept, {new} new")
        time.sleep(PAUSE_BETWEEN_REQUESTS)

    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=FEED_RETENTION_DAYS)).isoformat()
    job_list = [j for j in jobs.values() if (j.get("lastSeen") or j.get("firstSeen") or "") >= cutoff]
    jobs = {j["id"]: j for j in job_list}
    collapsed = collapse_wiki_duplicates(jobs)
    if collapsed:
        print(f"[dedup] Consolidated {collapsed} renamed wiki entries using their specific official job-call URLs")

    profile = load_profile()
    if profile["terms"]:
        print(f"[score] {len(profile['terms'])} profile terms; reading posting pages…")
        fetched = apply_scores(jobs, profile, today)
        scored = sum(1 for j in jobs.values() if "score" in j)
        print(f"        -> read {fetched} pages this run; {scored} postings scored")
    else:
        apply_scores(jobs, profile, today)

    cross=collapse_cross_source_duplicates(jobs)
    if cross:
        print(f"[dedup] Consolidated {cross} cross-source advertisements pointing to the same official requisition")
    job_list = list(jobs.values())
    job_list.sort(key=lambda j: (j.get("firstSeen") or "", j.get("title") or ""), reverse=True)
    feed = {"schemaVersion": 1, "generatedAt": today, "profileUpdatedAt": profile["updatedAt"], "sources": statuses, "jobs": job_list[:MAX_FEED_JOBS]}
    save_json(FEED_PATH, feed)
    print(f"Feed written: {len(feed['jobs'])} postings from {len(statuses)} sources.")


def run_check(url):
    checks = load_json(CHECKS_PATH, {"checks": {}})
    url = url.strip()
    print(f"[check] {url}")
    try:
        result, posts = collect_source(url, "auto")
    except Exception as e:  # noqa: BLE001 — a bad page must never crash the workflow
        result, posts = {"url": url, "status": "error", "httpStatus": None, "kind": "auto", "title": "", "error": clean_text(str(e), 200)}, []
    host = urllib.parse.urlsplit(url).netloc.replace("www.", "")
    rec = {
        "url": url, "status": result["status"], "httpStatus": result["httpStatus"], "kind": result["kind"], "title": result["title"], "error": result["error"],
        "jobLinksFound": len(posts), "sample": [{"title": p["title"], "institution": p.get("institution", ""), "url": p["url"], **({"statuses": p["statuses"][-2:]} if p.get("statuses") else {})} for p in posts[:5]],
        "suggestedName": result["title"] or host, "checkedAt": now_iso(),
    }
    checks.setdefault("checks", {})[url] = rec
    items = sorted(checks["checks"].items(), key=lambda kv: kv[1].get("checkedAt", ""), reverse=True)[:50]
    checks["checks"] = dict(items)
    save_json(CHECKS_PATH, checks)
    print(f"        -> {rec['status']} (http {rec['httpStatus']}), {rec['jobLinksFound']} postings")
    for p in rec["sample"]:
        print(f"           - {p['title']}  [{p['institution']}]")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="ignore weekly cadence")
    ap.add_argument("--check", metavar="URL", help="check one URL and record the verdict")
    args = ap.parse_args()
    if args.check:
        run_check(args.check)
    else:
        # Manual and push-triggered runs always check everything; only the schedule respects cadence.
        force = args.force or os.environ.get("GITHUB_EVENT_NAME", "") not in ("schedule", "")
        run_all(force=force)


if __name__ == "__main__":
    main()
