"use strict";
// Read-only extraction over SSH. Never export names, addresses, sessions or passwords.
const {DatabaseSync} = require("node:sqlite");
const {createHash} = require("node:crypto");
const path = require("node:path");
function extract(file, since = "2026-10-01") {
  const db = new DatabaseSync(file, {readOnly: true});
  try {
    db.exec("PRAGMA busy_timeout=5000; BEGIN");
    const exists = name => Boolean(db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(name));
    const key = value => createHash("sha256").update(value.normalize("NFKC").trim().toLowerCase()).digest("hex");
    const users = db.prepare("SELECT id,email,created_at FROM users").all();
    const identities = new Map(users.map(row => [row.id, key(row.email)]));
    const map = rows => rows.map(({user_id,...row}) => ({...row, key: identities.get(user_id) || null}));
    const setting = name => db.prepare("SELECT setting_value FROM settings WHERE setting_key=?").get(name)?.setting_value || null;
    const result = {
      accounts: users.map(row => ({key: identities.get(row.id), createdAt: row.created_at})),
      usageStarted: setting("edition_usage_started_at"), readsStarted: setting("group_reads_started_at"),
      usage: map(db.prepare("SELECT user_id,date_key FROM user_usage_daily WHERE date_key>=?").all(since)),
      reads: exists("user_article_reads") ? map(db.prepare("SELECT user_id,date_key,COUNT(*) AS count FROM user_article_reads WHERE date_key>=? GROUP BY user_id,date_key").all(since)) : [],
      likes: map(db.prepare("SELECT user_id,date(created_at,'+9 hours') AS date_key,COUNT(*) AS count FROM user_likes WHERE date(created_at,'+9 hours')>=? GROUP BY user_id,date_key").all(since)),
      comments: map(db.prepare("SELECT user_id,date(created_at,'+9 hours') AS date_key,COUNT(*) AS count FROM comments WHERE date(created_at,'+9 hours')>=? GROUP BY user_id,date_key").all(since)),
      access: db.prepare("SELECT date_key,visit_count FROM access_daily WHERE date_key>=?").all(since),
    };
    db.exec("COMMIT");
    return result;
  } finally { db.close(); }
}
if (require.main === module) {
  const root = process.argv[2] || "C:/Users/Administrator/Desktop";
  const since = process.argv[3] || "2026-10-01";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(since)) throw new Error("Invalid start date");
  const result = {};
  for (const [edition,folder] of [["interior","DailyNews"],["exterior","DailyNewsExterior"]]) result[edition] = extract(path.join(root,folder,"data/dailynews.sqlite"), since);
  process.stdout.write(JSON.stringify(result));
}
module.exports = {extract};
