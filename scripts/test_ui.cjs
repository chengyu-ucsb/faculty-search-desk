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
  S:{tracker:{jobs:[]},feed:{jobs:[]}},URL,Map,Set
};
vm.createContext(mock);
vm.runInContext(code,mock);
const job={id:'j1',title:'Assistant Professor',institution:'University of North Dakota',jobNumber:'12345',url:'https://und.edu/job/12345'};
mock.S.tracker.jobs.push(job);
let idx=mock.trackerIndex();
assert.equal(mock.trackerJobForFeed({id:'other',title:'Assistant Professor',institution:'University of North Dakota',jobNumber:'67890',url:'https://und.edu/job/67890'},idx),null,'different posting numbers must not collapse');
assert.equal(mock.trackerJobForFeed({id:'another',title:'Assistant Professor',institution:'Another University',jobNumber:'12345',url:'https://another.edu/job/12345'},idx),null,'same number at another university is not enough');
assert.equal(mock.trackerJobForFeed({id:'same',title:'Assistant Professor',institution:'University of North Dakota',jobNumber:'12345',url:'https://und.edu/job/12345'},idx)?.id,'j1');
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
  console.log('UI syntax, privacy, deduplication and upload fingerprint checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
