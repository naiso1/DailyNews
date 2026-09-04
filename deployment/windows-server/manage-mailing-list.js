"use strict";

const fs = require("fs");
const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const root = path.resolve(__dirname, "..");
const databaseFile = path.join(root, "data", "dailynews.sqlite");

if (!fs.existsSync(databaseFile)) {
  throw new Error(`Database was not found: ${databaseFile}`);
}

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

function validEmail(value) {
  return value.length >= 5 && value.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

const db = new DatabaseSync(databaseFile);
db.exec(`
  PRAGMA foreign_keys = ON;
  PRAGMA busy_timeout = 5000;
  CREATE TABLE IF NOT EXISTS mail_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    user_id INTEGER UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'manual'
      CHECK (source IN ('manual', 'registered_user')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
  );
`);

const command = process.argv[2] || "export-json";

try {
  if (command === "export-json") {
    const recipients = db.prepare(`
      SELECT email, COALESCE(display_name, '') AS display_name, source
      FROM mail_subscriptions
      WHERE enabled = 1
      ORDER BY email
    `).all().map((row) => ({
      email: row.email,
      displayName: row.display_name,
      source: row.source,
    }));
    process.stdout.write(`${JSON.stringify({
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      recipientCount: recipients.length,
      to: recipients.map((recipient) => recipient.email).join(";"),
      recipients,
    })}\n`);
  } else if (command === "import-file") {
    const sourceFile = process.argv[3];
    if (!sourceFile) throw new Error("Usage: manage-mailing-list.js import-file <json-file>");
    const parsed = JSON.parse(fs.readFileSync(sourceFile, "utf8"));
    const values = Array.isArray(parsed) ? parsed : parsed.recipients;
    if (!Array.isArray(values)) throw new Error("The import file must contain an array of recipients.");
    const insert = db.prepare(`
      INSERT OR IGNORE INTO mail_subscriptions(email, display_name, source)
      VALUES (?, ?, 'manual')
    `);
    let added = 0;
    db.exec("BEGIN IMMEDIATE");
    try {
      for (const value of values) {
        const email = normalizeEmail(typeof value === "string" ? value : value.email);
        const displayName = typeof value === "object" && value
          ? String(value.displayName || "").trim().slice(0, 40)
          : "";
        if (!validEmail(email)) continue;
        added += Number(insert.run(email, displayName || null).changes || 0);
      }
      db.exec("COMMIT");
    } catch (error) {
      db.exec("ROLLBACK");
      throw error;
    }
    process.stdout.write(`${JSON.stringify({ imported: added, supplied: values.length })}\n`);
  } else {
    throw new Error(`Unknown command: ${command}`);
  }
} finally {
  db.close();
}
