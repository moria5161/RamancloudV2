import test from 'node:test';
import assert from 'node:assert/strict';
import {addPlanToTimeline,updateTimelinePlan,chatHistory} from '../src/components/qaTimeline.js';

test('plans retain their position between discussion and later questions',()=>{
 const messages=[{role:'user',content:'denoise'},{role:'assistant',content:'use sg'}];
 const first={id:'one',status:'draft'};
 const timeline=[...addPlanToTimeline(messages,first),{role:'user',content:'refine baseline'}];
 const updated=updateTimelinePlan(timeline,{...first,status:'completed'});
 assert.equal(updated[2].plan.status,'completed');
 assert.equal(updated[3].content,'refine baseline');
 assert.deepEqual(chatHistory(updated),[...messages,timeline[3]]);
 const next=addPlanToTimeline(updated,{id:'two',status:'draft'});
 assert.equal(next[2].plan.id,'one');assert.equal(next[4].plan.id,'two');
 assert.equal(next[2].plan.status,'completed');
});

test('a replacement disables previous draft without moving or duplicating it',()=>{
 const first=addPlanToTimeline([],{id:'one',status:'draft'});
 const next=addPlanToTimeline([...first,{role:'user',content:'change'}],{id:'two',status:'draft'});
 assert.equal(next[0].plan.status,'superseded');
 assert.equal(next[1].content,'change');
 assert.equal(addPlanToTimeline(next,{id:'two',status:'running'}).length,3);
 assert.equal(next[2].plan.status,'draft'); // immutable state
});
