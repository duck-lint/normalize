'use strict';
// No browser/runtime dependency: verify displayed totals from real group schema.
const test=require('node:test');
const assert=require('node:assert/strict');
const {summarize,retainedOrNext}=require('../review_ui/metrics.js');

function group(key,count,repairs,verified,eligible,known=false){
  return {key,word:key,count,repair_count:repairs,verified_repair_count:verified,
    eligible_count:eligible,already_known:known};
}
const all=[
  group('ofthe',12,12,12,0),
  group('newtonic',4,1,1,3),
  group('liberte',3,0,0,3),
  group('repaired-but-unverified',8,8,5,0),
  group('already-known',2,0,0,2,true)
];
const decisions={
  'newtonic':{decision:'accepted'},
  'liberte':{decision:'rejected'}
};

test('whole-book totals distinguish lexical types from scan occurrences',()=>{
  assert.deepEqual(summarize(all,decisions),{
    forms:5,occurrences:29,pending:3,accepted:1,rejected:1,
    proposedOccurrences:21,verifiedOccurrences:18,
    eligibleForms:2,bulkEligibleForms:1
  });
});

test('filtered status shows the real displayed totals, not the whole book',()=>{
  const pending=all.filter(g=>!decisions[g.key]);
  assert.deepEqual(summarize(pending,decisions),{
    forms:3,occurrences:22,pending:3,accepted:0,rejected:0,
    proposedOccurrences:20,verifiedOccurrences:17,
    eligibleForms:0,bulkEligibleForms:1
  });
  const approvedOnly=all.filter(g=>g.verified_repair_count===g.count);
  assert.equal(summarize(approvedOnly,decisions).forms,1);
  assert.equal(summarize(approvedOnly,decisions).occurrences,12);
  assert.equal(summarize(approvedOnly,decisions).verifiedOccurrences,12);
});

test('empty filtered list reports zero everywhere',()=>{
  for(const number of Object.values(summarize([],decisions)))assert.equal(number,0);
});

test('no candidate becomes eligible for bulk lexicon rejection from mere proposals',()=>{
  const summary=summarize([all[3]],{});
  assert.equal(summary.proposedOccurrences,8);
  assert.equal(summary.verifiedOccurrences,5);
  assert.equal(summary.bulkEligibleForms,0);
  assert.equal(summarize([all[0]],{'ofthe':{decision:'rejected'}}).bulkEligibleForms,0);
  assert.equal(summarize([group('known',2,2,2,0,true)],{}).bulkEligibleForms,0);
});

test('selection after a filter or status change preserves nearby position',()=>{
  assert.equal(retainedOrNext(all,'newtonic',3),'newtonic');
  assert.equal(retainedOrNext(all.slice(2),'newtonic',1),'repaired-but-unverified');
  assert.equal(retainedOrNext(all.slice(2),'newtonic',99),'already-known');
  assert.equal(retainedOrNext(all.slice(2),'newtonic',-2),'liberte');
  assert.equal(retainedOrNext([],'newtonic',0),null);
});
