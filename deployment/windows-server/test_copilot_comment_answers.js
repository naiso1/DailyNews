'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {DatabaseSync}=require('node:sqlite');
const {createStore}=require('./copilot-comment-answers');
function fixture(){
 const db=new DatabaseSync(':memory:');db.exec(`PRAGMA foreign_keys=ON;
 CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT);INSERT INTO users VALUES(1,'alice@example.test'),(2,'bob@example.test');
 CREATE TABLE comments(id INTEGER PRIMARY KEY,item_id TEXT,user_id INTEGER,comment_text TEXT);
 INSERT INTO comments VALUES(7,'jp1',1,'@Copilot 仕様は？');`);
 const alice={id:1,email:'alice@example.test'},bob={id:2,email:'bob@example.test'};
 const job={id:'a'.repeat(64),itemId:'jp1',commentId:7,status:'done',answer:'記事からは確認できません。',completedAt:'2026-11-19T04:00:00Z',conversationUrl:'https://copilot.cloud.microsoft/chat/private',sendAttemptCount:1};
 return {db,alice,bob,job};
}
test('legacy/private and other-member answers are not published implicitly',()=>{
 const {db,alice,bob,job}=fixture(),store=createStore({db,readJob:async()=>job});
 try{assert.equal(store.record(alice,job),null);assert.throws(()=>store.publish(bob,job),{safeCode:'NOT_FOUND'});
 assert.throws(()=>store.publish(alice,{...job,scope:'new'}),{safeCode:'INVALID_REQUEST'});
 assert.equal(store.publicAnswer(7),null);store.consent(alice,'jp1',7);assert.equal(store.record(bob,job),null);
 assert.equal(store.publicAnswer(7).status,'waiting');}finally{store.close();db.close();}
});
test('pending answers survive store restart and polling only retrieves the saved job',async()=>{
 const {db,alice,job}=fixture();let reads=0;
 let store=createStore({db,intervalMs:60000,readJob:async()=>job});
 store.consent(alice,'jp1',7);store.record(alice,{...job,status:'queued',answer:undefined});store.close();
 db.prepare('UPDATE copilot_comment_answers SET next_poll_at=0').run();
 store=createStore({db,intervalMs:60000,readJob:async(user,id)=>{reads++;assert.equal(user.email,alice.email);assert.equal(id,job.id);return job;}});
 try{await store.poll();assert.equal(reads,1);assert.deepEqual(store.publicAnswer(7),{status:'published',answer:job.answer,completedAt:new Date(job.completedAt).toISOString()});
 await store.poll();assert.equal(reads,1);assert.equal(db.prepare('SELECT COUNT(*) n FROM comments').get().n,1);
 assert.equal(store.record(alice,{...job,answer:'duplicate changed text'}).answer,job.answer);
 }finally{store.close();db.close();}
});
test('deleting a question removes its published answer and late results cannot restore it',()=>{
 const {db,alice,job}=fixture(),store=createStore({db,readJob:async()=>job});
 try{store.publish(alice,job);db.prepare('DELETE FROM comments WHERE id=7').run();assert.equal(store.publicAnswer(7),null);assert.equal(store.record(alice,job),null);}finally{store.close();db.close();}
});
test('unknown outcomes stay unavailable and changed questions cannot acquire an old answer',()=>{
 const {db,alice,job}=fixture(),store=createStore({db,readJob:async()=>job});
 try{store.consent(alice,'jp1',7);store.record(alice,{...job,status:'needs_review'});assert.deepEqual(store.publicAnswer(7),{status:'unavailable'});
 db.prepare("UPDATE comments SET comment_text='別の質問' WHERE id=7").run();assert.throws(()=>store.record(alice,job),{safeCode:'STALE_QUESTION'});
 assert.equal(store.publicAnswer(7).answer,undefined);}finally{store.close();db.close();}
});
