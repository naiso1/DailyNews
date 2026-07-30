"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const backupDirectory = path.join(root, "backups");
const sources = [
  path.join(root, "public", "data.json"),
  path.join(root, "data", "reactions.json"),
];
const retentionDays = 35;
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "Z");
const destination = path.join(backupDirectory, `interiorgram_${stamp}`);

fs.mkdirSync(destination, { recursive: true });

for (const source of sources) {
  if (fs.existsSync(source)) {
    fs.copyFileSync(source, path.join(destination, path.basename(source)));
  }
}

const cutoff = Date.now() - retentionDays * 24 * 60 * 60 * 1000;
for (const entry of fs.readdirSync(backupDirectory, { withFileTypes: true })) {
  if (!entry.isDirectory() || !entry.name.startsWith("interiorgram_")) continue;
  const target = path.join(backupDirectory, entry.name);
  if (fs.statSync(target).mtimeMs < cutoff) {
    fs.rmSync(target, { recursive: true, force: true });
  }
}

process.stdout.write(`${destination}\n`);
