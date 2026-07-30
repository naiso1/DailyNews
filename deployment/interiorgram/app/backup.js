"use strict";

const fs = require("fs");
const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const ROOT = path.resolve(__dirname, "..");
const DB_FILE = path.join(ROOT, "data", "interiorgram.sqlite");
const BACKUP_DIR = path.join(ROOT, "backups");
const RETENTION_DAYS = 35;

if (!fs.existsSync(DB_FILE)) {
  throw new Error(`Interiorgram database was not found: ${DB_FILE}`);
}

fs.mkdirSync(BACKUP_DIR, { recursive: true });
const now = new Date();
const stamp = now
  .toISOString()
  .replaceAll("-", "")
  .replaceAll(":", "")
  .replace(/\.\d{3}Z$/, "Z");
const destination = path.join(BACKUP_DIR, `interiorgram_${stamp}.sqlite`);
const escapedDestination = destination.replaceAll("'", "''");

const db = new DatabaseSync(DB_FILE);
try {
  db.exec(`VACUUM INTO '${escapedDestination}'`);
} finally {
  db.close();
}

const cutoff = Date.now() - RETENTION_DAYS * 24 * 60 * 60 * 1000;
for (const entry of fs.readdirSync(BACKUP_DIR, { withFileTypes: true })) {
  if (!entry.isFile() || !/^interiorgram_\d{8}T\d{6}Z\.sqlite$/.test(entry.name)) {
    continue;
  }
  const file = path.join(BACKUP_DIR, entry.name);
  if (fs.statSync(file).mtimeMs < cutoff) {
    fs.unlinkSync(file);
  }
}

process.stdout.write(`Interiorgram backup created: ${destination}\n`);
