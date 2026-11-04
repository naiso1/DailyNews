"use strict";
const assert = require("node:assert/strict");
const {DatabaseSync} = require("node:sqlite");
const {syncRoster} = require("../deployment/windows-server/roster-mailing-list");
const db = new DatabaseSync(":memory:");
db.exec(`CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT UNIQUE);
CREATE TABLE mail_subscriptions(email TEXT PRIMARY KEY,display_name TEXT,user_id INTEGER UNIQUE,
enabled INTEGER,source TEXT);
INSERT INTO users VALUES(1,'registered@toyoda-gosei.co.jp');
INSERT INTO mail_subscriptions VALUES('off@toyoda-gosei.co.jp','Off',NULL,0,'manual');`);
const row = (name, room="内装開発室") => ({email:name+"@toyoda-gosei.co.jp",displayName:name,room});
const payload = {schema:1,edition:"interior",masterDate:"2026-11-02",masterHash:"a".repeat(64),
  memberCount:48,recipients:[row("new"),row("off"),row("registered")]};
const count = () => db.prepare("SELECT count(*) n FROM mail_subscriptions").get().n;
assert.equal(syncRoster(db,payload,"interior",{dryRun:true}).added,2);
assert.equal(count(),1, "Preview must not change subscriptions");
assert.equal(db.prepare("SELECT count(*) n FROM sqlite_master WHERE name='roster_mail_state'").get().n,0);
const first = syncRoster(db,payload,"interior");
assert.equal(first.added,2);
assert.equal(first.disabledExisting,1);
assert.equal(db.prepare("SELECT enabled FROM mail_subscriptions WHERE email=?").get(row("off").email).enabled,0);
assert.equal(db.prepare("SELECT user_id FROM mail_subscriptions WHERE email=?").get(row("registered").email).user_id,1);
assert.equal(db.prepare("SELECT count(*) n FROM users").get().n,1, "No accounts created");
assert.equal(syncRoster(db,payload,"interior").added,0, "Retry is idempotent");
db.prepare("DELETE FROM mail_subscriptions WHERE email=?").run(row("new").email);
assert.equal(syncRoster(db,payload,"interior").previouslySeen,1, "Deletion remains effective");
assert.equal(count(),2);
for (const bad of [
  {...payload,edition:"exterior"},
  {...payload,recipients:[row("cross","外装開発室")]},
  {...payload,recipients:[row("repeat"),row("repeat")]},
  {...payload,recipients:[{...row("external"),email:"x@external.example"}]},
  {...payload,memberCount:100},
  {...payload,masterDate:"2026-10-01"},
]) {
  assert.throws(()=>syncRoster(db,bad,"interior"));
  assert.equal(count(),2, "Rejected master cannot partially enroll people");
}
// New people in the next master are enrolled, while a stopped recipient stays stopped.
const next = {...payload, masterDate:"2026-11-03",masterHash:"b".repeat(64),memberCount:49,
  recipients:[...payload.recipients,row("later")]};
assert.equal(syncRoster(db,next,"interior").added,1);
assert.equal(db.prepare("SELECT enabled FROM mail_subscriptions WHERE email=?").get(row("off").email).enabled,0);
assert.throws(()=>syncRoster(db,{...next,memberCount:1,recipients:[row("shrink")]},"interior"));
assert.equal(count(),3);
db.close();
console.log("PASS roster mail enrollment: preview, edition isolation, choices, deletion, retries, validation, growth guards");
