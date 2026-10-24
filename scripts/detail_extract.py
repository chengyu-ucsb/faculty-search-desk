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
    r"\b(?:priority(?: review| consideration)?|full consideration|initial review|"
    r"review of applications(?: will)? (?:begin|start)s?|"
    r"review(?:ing)? (?:will )?(?:begin|start)s?|review (?:start|date)|"
    r"screening (?:of )?(?:applicants|applications?) (?:will )?begin|"
    r"screening (?:begins|starts)|application deadline|apply by|"
    r"applications? (?:must|should|are to) be (?:received|submitted)|"
    r"(?:materials|applications?) (?:must be |are )?(?:due|received by)|"
    r"(?:materials|applications?) (?:must|should) be submitted|"
    r"applications? (?:will )?close|closing date|close date|closes? on|deadline)\b", re.I)
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
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}",value):
        try: return dt.date.fromisoformat(value).isoformat()
        except ValueError: return ""
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
        # A heading and its date may be separate nodes; never borrow an
        # arbitrary following paragraph or infer the year from today's date.
        if DATE_CONTEXT.search(line) and not DATE_TEXT.search(line) and i+1<len(lines):
            following=lines[i+1].strip()
            if len(following)<90 and DATE_TEXT.match(following):
                line += " " + following
        # Associate each date with its own clause. A single paragraph often
        # contains posted/start dates, a priority date and a hard cutoff.
        for clause in re.split(r";|(?<=[.!?])\s+(?=[A-Z])",line):
            contexts=list(DATE_CONTEXT.finditer(clause))
            dates=list(DATE_TEXT.finditer(clause))
            for date_match in dates:
                if not contexts: continue
                # The closest label can be before OR after its date, e.g.
                # 'received by October 26, 2026 for full consideration'.
                nearby=[c for c in contexts if abs(c.start()-date_match.start())<180]
                if not nearby: continue
                preceding=[c for c in nearby if c.start()<date_match.start()]
                context=preceding[-1] if preceding else nearby[0]
                # Do not attach a later deadline label across another date.
                if context.start()>date_match.start() and any(
                        date_match.end()<d.start()<context.start() for d in dates): continue
                start=context.start() if context.start()<date_match.start() else date_match.start()
                segment=clause.strip()  # keep qualifiers and cutoff times in the source quote
                # A leading unrelated date should not inherit a later label.
                prefix=clause[:date_match.start()]
                unrelated = r"\b(?:posted|published|posting date|start date|appointment|employment begins?|position begins?|listing expir(?:y|es|ation)|valid through)\b"
                # A deadline label must not spill across an intervening event
                # label, even when both dates occur in the same sentence.
                between=clause[context.end():date_match.start()] if preceding else prefix
                if re.search(unrelated,between,re.I): continue
                date=date_value(date_match.group())
                if not date: continue
                previous_end=max([d.end() for d in dates if d.end()<=date_match.start()] or [0])
                local=clause[previous_end:date_match.end()]
                if re.match(r"\s*(?:for\s+)?full consideration",clause[date_match.end():],re.I):
                    local += " full consideration"
                if re.search(r"full consideration",local,re.I): rule="full_consideration"
                elif re.search(r"priority",local,re.I): rule="priority"
                elif re.search(r"review|screening",context.group(),re.I): rule="review"
                else: rule="closing"
                item={"date":date,"type":rule,"evidence":segment[:380],"url":url,"source":kind}
                tail=clause[start:date_match.start()] + " " + clause[date_match.end():min(len(clause),date_match.end()+90)]
                tm=re.search(r"\b(?:at\s+|by\s+)?(\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?|\d{1,2}\s*[ap]\.?m\.?)",tail,re.I)
                zone=re.search(r"\b(?:EDT|EST|CDT|CST|MDT|MST|PDT|PST|UTC|Eastern(?: Standard| Daylight)?(?: Time)?|Central(?: Standard| Daylight)?(?: Time)?|Mountain(?: Standard| Daylight)?(?: Time)?|Pacific(?: Standard| Daylight)?(?: Time)?)\b",tail,re.I)
                if tm:item["timeText"]=tm.group(1).strip()
                if zone:item["timezoneText"]=zone.group().strip()
                deadlines.append(item)
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
        k=(x["date"],x["type"],x.get("timeText"),x.get("timezoneText"))
        if k not in keys:uniq.append(x);keys.add(k)
    return {"deadlineEvidence":uniq[:20],"materialEvidence":material,"hasApplicationSection":bool(windows)}

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
    for field, key in (("deadlineEvidence", lambda x: (x["date"], x["type"], x.get("url"), x.get("source"), x.get("timeText"), x.get("timezoneText"))),
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


def resolve_deadlines(evidence):
    """Choose a source-backed event, or explicitly decline conflicting dates.

    Priority/review events are not conflicts with a closing date. Metadata
    expiration alone is not proof of an application cutoff. Source rank only
    resolves the same event type, never converts a review into a hard deadline.
    """
    candidates=[dict(x) for x in evidence if date_value(x.get("date", ""))
                and x.get("type") in {"closing","priority","full_consideration","review"}
                and x.get("source")!="structured-data"]
    rank={"official-job-call":3,"linked-call":2,"job-board":1}
    for kind in ("closing","full_consideration","priority","review"):
        group=[x for x in candidates if x["type"]==kind]
        if not group: continue
        strongest=max(rank.get(x.get("source"),0) for x in group)
        top=[x for x in group if rank.get(x.get("source"),0)==strongest]
        dates={x["date"] for x in top}
        times={x["timeText"].lower().replace(" ","") for x in top if x.get("timeText")}
        zones={x["timezoneText"].lower() for x in top if x.get("timezoneText")}
        if len(dates)>1 or len(times)>1 or len(zones)>1:
            return {"status":"conflict","selected":None,"candidates":candidates,
                    "conflicts":top}
        chosen=top[0]
        # Preserve disagreement even when a clearly higher-ranked source wins.
        conflicts=[x for x in group if x["date"]!=chosen["date"]]
        return {"status":"resolved" if not conflicts else "resolved_with_conflict",
                "selected":chosen,"candidates":candidates,"conflicts":conflicts}
    return {"status":"unverified","selected":None,"candidates":[],"conflicts":[]}
