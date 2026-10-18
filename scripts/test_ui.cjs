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
assert.equal(mock.discoveryEligible({...officialUt,statuses:[]}),true,
  'an active job without interview updates should still be discoverable');
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
