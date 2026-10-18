"""Conservative extraction of verifiable job-application information.

Source links are candidates, never proof of requirements. A listing may expose
only a teaser or have an inaccessible apply portal. Evidence is always attached
to the exact URL and quote from which it came.
"""
import datetime as dt
import re
import urllib.parse
from bs4 import BeautifulSoup

APPLY_HEADING = re.compile(
    r"\b(?:how to apply|application (?:materials|instructions|procedure|requirements)|"
    r"required (?:application )?materials|documents to (?:submit|upload)|"
    r"to apply|please (?:upload|submit)|submit (?:an?|the|your)|"
    r"(?:candidates|applicants) (?:must|should|will|are asked to) (?:provide|submit|upload|include)|"
    r"(?:application|application package|materials) (?:should|must|will) (?:include|contain)|"
    r"what (?:you|applicants) (?:will )?need|position announcement|"
    r"applications? (?:must|should|are|will) (?:be )?submitted)\b", re.I)
DATE_CONTEXT = re.compile(
    r"\b(?:priority|full consideration|initial review|review of applications|"
    r"review(?:ing)? (?:will )?begin|screening (?:of )?(?:applicants|applications?) (?:will )?begin|"
    r"screening (?:begins|starts)|application deadline|apply by|"
    r"applications? (?:must|should|are to) be (?:received|submitted)|"
    r"closing date|deadline)\b", re.I)
DATE_TEXT = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|"
    r"\b20\d{2}-\d{2}-\d{2}\b",re.I)
MATERIALS = {
    "cover_letter": re.compile(r"\b(?:cover(?:ing)? letter|letter of (?:interest|application|intent))\b",re.I),
    "cv": re.compile(r"\b(?:curriculum vitae|résumé|resume\b|\bcv\b)",re.I),
    "research_statement": re.compile(r"\b(?:research statement|statement of research|research (?:interests|plans|agenda))\b",re.I),
    "teaching_statement": re.compile(r"\b(?:teaching statement|statement of teaching|teaching philosophy)\b",re.I),
    "teaching_evals": re.compile(r"\b(?:teaching evaluations?|student evaluations? of teaching)\b",re.I),
    "writing_sample": re.compile(r"\b(?:writing sample|scholarly (?:paper|article)|publication sample|sample of (?:written|scholarly) work)\b",re.I),
    "reference_names": re.compile(r"\b(?:contact information for|names and contact information of|list of)\s+(?:\w+\s+){0,3}(?:references?|referees)\b",re.I),
    "reference_letters": re.compile(r"\b(?:letters? of (?:recommendation|reference)|recommendation letters?)\b",re.I),
    "transcripts": re.compile(r"\b(?:transcripts?|academic records?)\b",re.I),
    "dei_statement": re.compile(r"\b(?:diversity (?:statement|essay)|statement (?:on|of) (?:diversity|inclusion))\b",re.I),
    "syllabus": re.compile(r"\b(?:syllabi|syllabus|course outlines?)\b",re.I),
    "service_statement": re.compile(r"\b(?:service statement|statement of service)\b",re.I),
}
LATER = re.compile(r"\b(?:finalists?|shortlisted|semi-finalists?|later stage|upon request|"
                   r"will be (?:requested|contacted) (?:later|after)|if invited)\b",re.I)
NEGATIVE = re.compile(r"\b(?:not required|do not submit|please do not include|optional)\b",re.I)
MONTHS={m:i for i,m in enumerate(("","jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec")) if m}
NOT_POSTING = re.compile(r"(?:/\b(?:privacy|terms|about|faculty|policies|benefits|"
                         r"contact|sign-?in|login|search|faq)\b)",re.I)
PREFERRED_LINK = re.compile(r"\b(?:apply(?: now| here| online)?|full (?:job |position )?description|"
                            r"job (?:details|posting)|see (?:the )?(?:job|posting)|"
                            r"application portal|official posting|view (?:position|details|job|posting)|position announcement|"
                            r"full (?:advertisement|announcement|call)|job (?:advertisement|ad)|"
                            r"position description|download (?:the )?(?:job|posting|advertisement|pdf)|"
                            r"complete (?:job |position )?posting|application information)\b",re.I)
BAD_LINK = re.compile(r"\b(?:share|similar jobs|other jobs|job alert|browse jobs|"
                      r"account|register|log in|sign in|privacy|terms)\b",re.I)

def text_lines(html):
    soup=BeautifulSoup(html,"html.parser")
    for tag in soup(["script","style","nav","header","footer","noscript","aside","iframe","form"]):
        tag.decompose()
    root=soup.find("main") or soup.find("article") or soup.body or soup
    for node in root.select("h1,h2,h3,h4,p,li,br,dt,dd"):
        node.insert_before("\n")
    return [re.sub(r"\s+"," ",part).strip() for part in root.get_text(" ",strip=True).split("\n") if part.strip()]

def date_value(s):
    m=DATE_TEXT.search(s)
    if not m: return ""
    value=re.sub(r"(?<=\d)(st|nd|rd|th)\b","",m.group()).replace(",","").replace(".","").strip()
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}",value): return value
    for fmt in ("%B %d %Y","%b %d %Y","%m/%d/%Y","%m-%d-%Y"):
        try: return dt.datetime.strptime(value,fmt).date().isoformat()
        except ValueError: pass
    return "" # an ambiguous yearless date is not safe to write to the tracker

def evidence_from_lines(lines,url,kind="posting"):
    """Return only explicit and contextual application evidence with source quotes."""
    deadlines=[]
    material=[]
    windows=[]
    for i,raw in enumerate(lines):
        line=re.sub(r"\s+"," ",raw).strip()
        if not line: continue
        ctx=" ".join(lines[max(0,i-1):min(len(lines),i+2)])[:700]
        for match in DATE_CONTEXT.finditer(line):
            # A listing may say "Posted: Jul 29; Apply By: Open until filled".
            # The posting date is not the application deadline.
            segment=line[match.start():]
            next_context=DATE_CONTEXT.search(segment,max(1,match.end()-match.start()))
            if next_context:segment=segment[:next_context.start()]
            segment=segment[:260]
            if re.search(r"open until filled|until (?:the )?position is filled|rolling applications?",segment[:100],re.I):
                continue
            date=date_value(segment)
            if not date and i+1<len(lines):
                next_line=lines[i+1].strip()
                if len(next_line)<48 and DATE_TEXT.search(next_line):
                    date=date_value(next_line)
                    if date:segment=(segment+" "+next_line).strip()
            if date:
                rule="priority" if re.search(
                    r"priority|full consideration|initial review|review.+begin|screening|consideration begins",
                    segment,re.I) else "closing"
                deadlines.append({"date":date,"type":rule,"evidence":segment[:380],"url":url,"source":kind})
        if APPLY_HEADING.search(line):
            windows.append(i)
    seen=set()
    for idx in windows:
        for i in range(idx,min(len(lines),idx+25)):
            line=lines[i].strip()
            if i>idx+8 and APPLY_HEADING.search(line):break
            if len(line)>750:continue
            for cat,rx in MATERIALS.items():
                if not rx.search(line):continue
                if i==idx and len(line)<28:continue
                # Exclude a bare "desired qualifications: excellent teaching" etc.
                if cat in seen:continue
                if cat in ("research_statement","teaching_statement") and not (
                    re.search(r"statement|philosophy|agenda|interests|plans",line,re.I)):continue
                status="later" if LATER.search(line) else "optional" if NEGATIVE.search(line) else "required"
                material.append({"category":cat,"status":status,"evidence":line[:380],"url":url,"source":kind})
                seen.add(cat)
    # De-duplicate deadline mentions, preferring the more precise official evidence.
    uniq=[];keys=set()
    for x in deadlines:
        k=(x["date"],x["type"])
        if k not in keys:uniq.append(x);keys.add(k)
    return {"deadlineEvidence":uniq[:5],"materialEvidence":material,"hasApplicationSection":bool(windows)}

def application_links(html,page_url):
    """Find actual 'Apply' links near a job, not every link in the page footer."""
    soup=BeautifulSoup(html,"html.parser")
    base=urllib.parse.urlsplit(page_url)
    candidates=[]
    for node in soup.select("a[href]"):
        label=re.sub(r"\s+"," ",node.get_text(" ",strip=True) or node.get("aria-label","")).strip()
        if not PREFERRED_LINK.search(label) or BAD_LINK.search(label):continue
        raw=node.get("href","")
        url=urllib.parse.urljoin(page_url,raw)
        parts=urllib.parse.urlsplit(url)
        if parts.scheme not in ("http","https") or not parts.netloc or NOT_POSTING.search(parts.path):continue
        if url.split("#",1)[0]==page_url.split("#",1)[0]:continue
        score=3 if "apply" in label.lower() else 2
        if any(term in parts.netloc.lower() for term in ("workday","jobs.","careers.","hr.","interfolio","recruit","peopleadmin","myu.","pageuppeople")):score+=2
        if parts.netloc!=base.netloc:score+=1
        candidates.append({"url":url,"label":label[:90],"score":score,"foundOn":page_url})
    dedup={}
    for x in candidates:
        dedup[x["url"]]=max(dedup.get(x["url"],x),x,key=lambda k:k["score"])
    return sorted(dedup.values(),key=lambda k:-k["score"])[:5]

def merge_evidence(primary, additional):
    """Combine source-backed facts without discarding facts from the first page."""
    merged = {"deadlineEvidence": [], "materialEvidence": [],
              "hasApplicationSection": bool(primary.get("hasApplicationSection") or additional.get("hasApplicationSection"))}
    for field, key in (("deadlineEvidence", lambda x: (x["date"], x["type"])),
                       ("materialEvidence", lambda x: (x["category"],))):
        seen = set()
        for item in additional.get(field, []) + primary.get(field, []):
            k = key(item)
            if k not in seen:
                merged[field].append(item)
                seen.add(k)
    return merged

def describe_coverage(evidence):
    if evidence.get("materialEvidence") and evidence.get("deadlineEvidence"):return "deadline_and_materials"
    if evidence.get("materialEvidence"):return "materials_only"
    if evidence.get("deadlineEvidence"):return "deadline_only"
    return "application_section_no_requirements" if evidence.get("hasApplicationSection") else "summary_only"
