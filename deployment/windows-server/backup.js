"use strict";

const fs = require("fs");
const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const root = path.resolve(__dirname, "..");
const dataDir = path.join(root, "data");
const databaseFile = path.join(dataDir, "dailynews.sqlite");
const backupDir = path.join(dataDir, "backups");

if (!fs.existsSync(databaseFile)) {
  throw new Error(`Database was not found: ${databaseFile}`);
}

fs.mkdirSync(backupDir, { recursive: true });
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const backupFile = path.join(backupDir, `dailynews_${stamp}.sqlite`);
const escapedBackupFile = backupFile.replace(/'/g, "''");

const db = new DatabaseSync(databaseFile);
try {
  db.exec(`VACUUM INTO '${escapedBackupFile}'`);
} finally {
  db.close();
}

const retentionMs = 35 * 24 * 60 * 60 * 1000;
const cutoff = Date.now() - retentionMs;
for (const entry of fs.readdirSync(backupDir, { withFileTypes: true })) {
  if (!entry.isFile() || !/^dailynews_.+\.sqlite$/.test(entry.name)) continue;
  const file = path.join(backupDir, entry.name);
  if (fs.statSync(file).mtimeMs < cutoff) {
    fs.unlinkSync(file);
  }
}

process.stdout.write(`DailyNews backup created: ${backupFile}\n`);
