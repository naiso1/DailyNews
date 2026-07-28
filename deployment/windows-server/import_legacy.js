"use strict";

const fs = require("fs");
const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const inputFile = process.argv[2];
if (!inputFile || !fs.existsSync(inputFile)) {
  throw new Error("Usage: node import_legacy.js <firebase-export.json>");
}

const root = path.resolve(__dirname, "..");
const databaseFile = path.join(root, "data", "dailynews.sqlite");
const payload = JSON.parse(fs.readFileSync(inputFile, "utf8"));
const db = new DatabaseSync(databaseFile);

db.exec("PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000;");
const upsertInteraction = db.prepare(`
  INSERT INTO interactions(item_id, likes, reads, updated_at)
  VALUES (?, ?, ?, CURRENT_TIMESTAMP)
  ON CONFLICT(item_id) DO UPDATE SET
    likes = MAX(interactions.likes, excluded.likes),
    reads = MAX(interactions.reads, excluded.reads),
    updated_at = CURRENT_TIMESTAMP
`);
const existingComments = db.prepare(
  "SELECT COUNT(*) AS count FROM comments WHERE item_id = ?",
);
const insertComment = db.prepare(`
  INSERT INTO comments(item_id, user_name, comment_text, client_id, created_at)
  VALUES (?, ?, ?, NULL, ?)
`);
const upsertDaily = db.prepare(`
  INSERT INTO access_daily(date_key, visit_count) VALUES (?, ?)
  ON CONFLICT(date_key) DO UPDATE SET
    visit_count = MAX(access_daily.visit_count, excluded.visit_count)
`);
const upsertTotal = db.prepare(`
  INSERT INTO settings(setting_key, setting_value) VALUES ('total_visits', ?)
  ON CONFLICT(setting_key) DO UPDATE SET
    setting_value = CAST(
      MAX(CAST(settings.setting_value AS INTEGER), CAST(excluded.setting_value AS INTEGER))
      AS TEXT
    )
`);

db.exec("BEGIN IMMEDIATE");
try {
  for (const [itemId, value] of Object.entries(payload.interactions || {})) {
    upsertInteraction.run(
      itemId,
      Math.max(0, Number(value.likes) || 0),
      Math.max(0, Number(value.reads) || 0),
    );
    if (Number(existingComments.get(itemId).count) === 0) {
      for (const comment of value.comments || []) {
        const text = String(comment.text || "").trim();
        if (!text) continue;
        insertComment.run(
          itemId,
          String(comment.user || "Guest").slice(0, 40),
          text.slice(0, 500),
          new Date(comment.date || Date.now()).toISOString(),
        );
      }
    }
  }

  const pageStats = payload.pageStats || {};
  for (const [dateKey, count] of Object.entries(pageStats.daily || {})) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) {
      upsertDaily.run(dateKey, Math.max(0, Number(count) || 0));
    }
  }
  upsertTotal.run(String(Math.max(0, Number(pageStats.total) || 0)));
  db.exec("COMMIT");
} catch (error) {
  db.exec("ROLLBACK");
  throw error;
} finally {
  db.close();
}

process.stdout.write(
  `Imported ${Object.keys(payload.interactions || {}).length} legacy interactions.\n`,
);
