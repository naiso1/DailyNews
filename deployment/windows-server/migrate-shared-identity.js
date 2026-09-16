"use strict";
const { migrate } = require("./shared-identity");
const args = process.argv.slice(2);
const value = (name) => args[args.indexOf(name) + 1];
if (!args.includes("--interior-db") || !args.includes("--exterior-db")) {
  throw new Error("Usage: node migrate-shared-identity.js --interior-db <absolute path> --exterior-db <absolute path> [--apply]");
}
const result = migrate(value("--interior-db"), value("--exterior-db"), args.includes("--apply"));
process.stdout.write(`${JSON.stringify(result)}\n`);
