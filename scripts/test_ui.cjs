// Offline checks for the UI. No browser, API calls, or user data are needed.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const src=fs.readFileSync('index.html','utf8');
const scripts=[...src.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
for(const body of scripts)new vm.Script(body); // parse all inline UI scripts
const start=src.indexOf('function normUrl('),end=src.indexOf('function feedInbox()');
assert(start>=0&&end>start);
const code=src.slice(start,end);
const mock={
  S:{tracker:{jobs:[]},feed:{jobs:[]}},URL,Map,Set,
  isWikiEntry:f=>Array.isArray(f.statuses)
};
vm.createContext(mock);
vm.runInContext(code,mock);
const job={id:'j1',title:'Assistant Professor',institution:'University of North Dakota',jobNumber:'12345',url:'https://und.edu/job/12345'};
mock.S.tracker.jobs.push(job);
let idx=mock.trackerIndex();
assert.equal(mock.trackerJobForFeed({id:'other',title:'Assistant Professor',institution:'University of North Dakota',jobNumber:'67890',url:'https://und.edu/job/67890'},idx),null,'different posting numbers must not collapse');
assert.equal(mock.trackerJobForFeed({id:'another',title:'Assistant Professor',institution:'Another University',jobNumber:'12345',url:'https://another.edu/job/12345'},idx),null,'same number at another university is not enough');
assert.equal(mock.trackerJobForFeed({id:'same',title:'Assistant Professor',institution:'University of North Dakota',jobNumber:'12345',url:'https://und.edu/job/12345'},idx)?.id,'j1');
const wikiBase={institution:'University of Texas, Austin (Austin, Texas)',sourceId:'academic-jobs-wiki',
    adUrl:'https://faculty.utexas.edu/career/188439',statuses:[],title:'Assistant Professor in Organizational Communication & Technology (Deadline: 09/15/2026)'};
const wikiOne={...wikiBase,id:'4db9e22f2195',firstSeen:'2026-09-07T17:20:46Z'};
const wikiTwo={...wikiBase,id:'91dffc54aeaf',firstSeen:'2026-10-09T17:28:48Z',
    title:wikiBase.title+' ZOOM INTERVIEW INVITATIONS SENT OUT'};
const chronicle={id:'4291024f17f0',institution:'University of Texas at Austin',
    title:'Assistant Professor, Tenure-Track Faculty Position in Organizational Communication',
    sourceId:'chronicle-communications',url:'https://jobs.chronicle.com/job/38051792/example',
    jobNumber:'38051792',deadline:'2026-12-13'};
const grouped=mock.groupRelatedFeed([wikiOne,wikiTwo,chronicle]);
assert.equal(grouped.length,2,'same official UT Austin requisition should be one discovery listing');
const wikiMerged=grouped.find(x=>x.sourceId==='academic-jobs-wiki');
assert.equal(wikiMerged.groupSize,1,'duplicate wiki headings must not offer Add separately');
assert.equal(wikiMerged.id,wikiOne.id,'preserve earliest canonical id');
assert(wikiMerged.statuses.includes('ZOOM INTERVIEW INVITATIONS SENT OUT'));
assert(!wikiMerged.title.includes('ZOOM INTERVIEW'));
assert(grouped.some(x=>x.id===chronicle.id),'different Chronicle requisition should remain distinct');

const consolidated={...wikiOne,
  alternateFeedIds:[wikiTwo.id,chronicle.id],
  alternateListings:[{id:chronicle.id,sourceId:chronicle.sourceId,url:chronicle.url}],
  deadline:'2026-09-15',deadlineKind:'priority'};
const alreadyTracked={id:'ut-old-chronicle',feedId:chronicle.id,
  institution:'University of Texas at Austin',title:chronicle.title,url:chronicle.url};
mock.S.tracker.jobs.push(alreadyTracked);
const aliasIndex=mock.trackerIndex();
assert.equal(mock.trackerJobForFeed(consolidated,aliasIndex)?.id,alreadyTracked.id,
  'a previously imported Chronicle listing must still match the canonical wiki posting');
mock.S.feed.jobs=[consolidated];
assert.equal(mock.matchFeedForJob(alreadyTracked)?.id,consolidated.id,
  're-linked feed ID must survive deduplication');

// Regression: the actual saved UT Austin position is at Zoom interview done.
const originalTracked={id:'ut-tracked',feedId:'4db9e22f2195',
  title:'Assistant Professor in Organizational Communication & Technology',
  institution:'University of Texas, Austin',stage:'zoom_done',outcome:'active'};
mock.S.tracker.jobs.push(originalTracked);
const officialUt={...consolidated,id:'4db9e22f2195',
  statuses:['Zoom interviews happening the week of Oct 5.','ZOOM INTERVIEW INVITATIONS SENT OUT']};
assert.equal(mock.trackerJobForFeed(officialUt,mock.trackerIndex())?.id,originalTracked.id,
  'UT Austin existing application must match current canonical feed ID');
assert.equal(mock.isAdvancedRecruitment(officialUt),true,
  'interview updates should not appear as new job opportunities');
assert.equal(mock.discoveryEligible(officialUt),false,
  'UT Austin must not appear in the default Discover view');
assert.equal(mock.discoveryEligible({...officialUt,statuses:[],newStatuses:[]}),false,
  'tracked UT Austin Zoom interview stage must be enough even if feed status is stale');
assert.equal(mock.discoveryEligible({id:'new-open-role',title:'Assistant Professor of Media Studies',institution:'Another Institution',statuses:[]}),true,
  'a new job without interview updates should still be discoverable');
mock.S.showAdvancedSearches=true;
assert.equal(mock.discoveryEligible(officialUt),true,
  'an explicit show interviewing searches choice should reveal the historical entry');
mock.S.showAdvancedSearches=false;
assert(src.includes("data-action-check=showadvanced"),
  'Discover must provide an explicit opt-in for searches already interviewing');

assert.equal(mock.specificWikiAdKey({...wikiBase,adUrl:'https://faculty.utexas.edu/'}),'',
    'generic department page cannot prove job identity');
assert.equal(mock.recognizableTitle('Assistant Professor'),false);
assert.equal(mock.recognizableTitle('Assistant Professor of Organizational Communication'),true);
assert(src.includes('class="workspace-sidebar"'), 'new desktop workspace shell present');
assert(src.includes('assets/workspace.css'), 'workspace stylesheet linked');
assert(src.includes('data-action="syncfeedall"'), 'bulk evidence synchronization available');
assert(!src.includes('const before=j.materials.length; addStandardMaterials(j);'), 'Discover must not add speculative generic requirements');
assert(src.includes("Personal files require a private repository"), 'guard against writing personal files to public repo');
const fingerprintStart=src.indexOf('async function gitBlobFingerprint(');
const fingerprintEnd=src.indexOf('/* ---------- uploads ---------- */',fingerprintStart);
assert(fingerprintStart>0&&fingerprintEnd>fingerprintStart, 'upload fingerprint helper present');
const testContext={crypto:require('node:crypto').webcrypto,TextEncoder,Uint8Array,Array,String};
vm.createContext(testContext);
vm.runInContext(src.slice(fingerprintStart,fingerprintEnd),testContext);
(async()=>{
  const bytes=new TextEncoder().encode('abc');
  const expected=require('node:crypto').createHash('sha1').update('blob 3'+String.fromCharCode(0)+'abc').digest('hex');
  const fingerprint=await testContext.gitBlobFingerprint(bytes.buffer);
  assert.equal(fingerprint,expected,'file SHA should match Git blob hash');
  console.log('UI syntax, privacy, discovery and upload fingerprint checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});

// Dates are evidence-bearing events, not interchangeable calendar strings.
const dateContext={Date,Map,Set,JSON,String,Array,URL,
  esc:x=>String(x??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'),
  fmtDate:x=>x,daysUntil:x=>x?Math.round((new Date(x+'T12:00:00Z')-new Date('2026-10-24T12:00:00Z'))/86400000):null,
  uid:()=> 'synthetic',label:()=>'',STANDARD_MATERIALS:[]};
vm.createContext(dateContext);
vm.runInContext(src.slice(src.indexOf('function deadlineType('),src.indexOf('function stagePill(')),dateContext);
vm.runInContext(src.slice(src.indexOf('const MONTHS ='),src.indexOf('const KERNED_WORDS')),dateContext);
vm.runInContext(src.slice(src.indexOf('function tidy('),src.indexOf('function labeled(')),dateContext);
vm.runInContext(src.slice(src.indexOf('function extractCallDeadlineEvidence('),src.indexOf('function parseJobCall(')),dateContext);
vm.runInContext(src.slice(src.indexOf('function syncFeedEvidence('),src.indexOf('const actions =')),dateContext);
const closing={date:'2026-10-31',type:'closing',evidence:'Application deadline: October 31, 2026',source:'official-job-call',url:'https://example.edu/job'};
const priority={date:'2026-10-06',type:'priority',evidence:'Priority: October 6, 2026',source:'official-job-call'};
let dates=dateContext.deadlineInfo({deadline:'2026-10-24',applicationEvidence:{deadlineEvidence:[priority,closing]}});
assert.equal(dates.selected.date,'2026-10-31');
assert.equal(dates.selected.type,'closing');
assert.equal(dates.conflict,true,'saved date/source discrepancy must be visible');
const savedMarkup=dateContext.deadlineCell({deadline:'2026-10-24',sourceEvidence:[closing]});
assert(savedMarkup.includes('2026-10-31')&&savedMarkup.includes('Saved date: 2026-10-24')&&savedMarkup.includes('Check date conflict'));
assert.equal(dateContext.jobActionDate({deadline:'2026-10-24',sourceEvidence:[closing]}),'2026-10-31','date sort/count must follow published event, not stale saved value');
assert.equal(dateContext.jobActionDate({deadline:'2026-10-24'}),'','legacy unknown dates must not trigger deadline urgency');
assert(dateContext.deadlineCell({deadline:'2026-10-24'}).includes('Saved date (unverified)'));
const conflict={deadline:'2026-10-25',verificationWarnings:['Source date conflicts with saved deadline.']};
assert.equal(dateContext.jobActionDate(conflict),'');
assert(dateContext.deadlineCell(conflict).includes('Check date conflict'));
for(const [kind,label] of [['priority','Priority consideration'],['full_consideration','Full consideration'],['review','Review starts']]){
 const row=dateContext.deadlineCell({deadline:'2026-10-26',sourceEvidence:[{date:'2026-10-26',type:kind}]});
 assert(row.includes(label));assert(!row.includes('Application deadline'));
}
assert.equal(dateContext.deadlineInfo({sourceEvidence:[closing,{...closing,date:'2026-11-01'}]}).selected,null,'two equally authoritative closing dates require review');
assert.equal(dateContext.deadlineInfo({sourceEvidence:[{...closing,date:'2026-10-20',source:'job-board'},closing]}).selected.date,'2026-10-31','official call outranks board');
assert.equal(dateContext.deadlineCandidates({deadlineEvidence:{date:'2026-11-20',type:'closing',source:'structured-data'}}).length,0,'ad expiry is not a closing deadline');
assert.equal(dateContext.deadlineCandidates({sourceEvidence:[{date:'2026-02-30',type:'closing'}]}).length,0);
const texts=[
 ['Priority given to applications received by October 6th, 2026. Application deadline: October 31, 2026.',['priority','closing']],
 ['Review of applications will begin immediately. For full consideration, please apply by October 26, 2026.',['full_consideration']],
 ['Review of applications begins November 2, 2026. Position is open until filled.',['review']],
 ['Applications must be received by November 1, 2026 at 6:00 pm Central Time.',['closing']],
 ['Posted October 1, 2026. Ad expires October 24, 2026. Position starts July 1, 2027.',[]],
 ['Application deadline: October 31.',[]],
 ['Application deadline\nOctober 31, 2026',['closing']],
 ['Date to be filled: July 1, 2027',[]]
];
for(const [text,kinds] of texts){
 const extracted=dateContext.extractCallDeadlineEvidence(text,2026);
 assert.deepEqual(Array.from(extracted,x=>x.type),kinds,text);
}
const jobToSync={deadline:'2026-10-24',targetDate:'2026-10-22',stage:'submitted',materials:[],verificationWarnings:['Keep existing review warning']};
const beforeSync=JSON.stringify(jobToSync);
const feedToSync={applicationEvidence:{deadlineEvidence:[priority,closing],materialEvidence:[]},verificationWarnings:[]};
assert(dateContext.syncFeedEvidence(jobToSync,feedToSync)>0);
assert.equal(jobToSync.deadline,'2026-10-24','sync must not overwrite saved date');
assert.equal(jobToSync.targetDate,'2026-10-22');assert.equal(jobToSync.stage,'submitted');
assert.equal(jobToSync.publishedDeadline,'2026-10-31');assert.equal(jobToSync.publishedDeadlineKind,'closing');
assert(jobToSync.verificationWarnings.includes('Keep existing review warning'));
assert.equal(dateContext.syncFeedEvidence(jobToSync,feedToSync),0,'repeated sync should be idempotent');
assert(src.includes('deadline:importedDate?.date')&&src.includes('deadlineKind:importedDate?.type')&&src.includes('deadlineEvidence:importedDate'),'import must select a single coherent evidence record');
console.log('Deadline type, conflict, extraction and saved-date preservation checks passed');

assert.equal(dateContext.deadlineInfo({sourceEvidence:[{...closing,timeText:'18:00'},{...closing,timeText:'23:59'}]}).selected,null,'conflicting source cutoff times require review');
assert.equal(dateContext.deadlineInfo({sourceEvidence:[{...closing,date:'2026-10-20',source:'job-board'},closing]}).conflict,true,'lower-authority conflicting dates remain visible');
assert.equal(dateContext.deadlineInfo({sourceEvidence:[{...closing,source:'',sourceType:'official_portal'},{...closing,date:'2026-10-20',source:'job-board'}]}).selected.date,'2026-10-31');

assert.equal(dateContext.extractCallDeadlineEvidence('Applications must be received by October 26, 2026 for full consideration.',2026)[0].type,'full_consideration');
assert.equal(dateContext.extractCallDeadlineEvidence('Applications must be received by October 26, 2026 for priority consideration.',2026)[0].type,'priority');

vm.runInContext(src.slice(src.indexOf('function applyParsedDeadline('),src.indexOf('function extractCallDeadlineEvidence(')),dateContext);
const parsedFields={deadline:closing.date,deadlineKind:closing.type,deadlineEvidence:closing,deadlineResolution:{status:'resolved',selected:closing,candidates:[closing]}};
const blankRefill={stage:'submitted',targetDate:'2026-10-22'};
assert(dateContext.applyParsedDeadline(blankRefill,parsedFields)>0);
assert.equal(blankRefill.deadline,closing.date);assert.equal(blankRefill.deadlineKind,closing.type);
assert.equal(blankRefill.deadlineEvidence.evidence,closing.evidence);
assert.equal(dateContext.jobActionDate(blankRefill),closing.date);
const savedRefill={deadline:'2026-10-24',targetDate:'2026-10-22',stage:'submitted'};
dateContext.applyParsedDeadline(savedRefill,parsedFields);
assert.equal(savedRefill.deadline,'2026-10-24');assert.equal(savedRefill.targetDate,'2026-10-22');assert.equal(savedRefill.stage,'submitted');
assert.equal(savedRefill.publishedDeadline,closing.date);assert.equal(dateContext.deadlineInfo(savedRefill).conflict,true);
assert.equal(dateContext.applyParsedDeadline(savedRefill,parsedFields),0);
assert(src.includes('let n = applyParsedDeadline(j,g.fields);'),'re-read call must retain date evidence');
