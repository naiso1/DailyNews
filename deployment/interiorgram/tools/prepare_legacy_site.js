"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const [sourceArgument, destinationArgument, webConfigArgument] =
  process.argv.slice(2);
if (!sourceArgument || !destinationArgument || !webConfigArgument) {
  process.stderr.write(
    "Usage: node prepare_legacy_site.js <source> <destination> <web.config>\n",
  );
  process.exit(2);
}

const source = path.resolve(sourceArgument);
const destination = path.resolve(destinationArgument);
const webConfig = path.resolve(webConfigArgument);
const requiredFiles = ["index.html", "style.css", "script.js", "data.js"];

for (const relativePath of requiredFiles) {
  const file = path.join(source, relativePath);
  if (!fs.statSync(file).isFile()) {
    throw new Error(`Required source file is missing: ${file}`);
  }
}
if (!fs.statSync(path.join(source, "images")).isDirectory()) {
  throw new Error(`Image directory is missing: ${path.join(source, "images")}`);
}
if (!fs.statSync(webConfig).isFile()) {
  throw new Error(`web.config is missing: ${webConfig}`);
}

fs.mkdirSync(destination, { recursive: true });
for (const relativePath of requiredFiles) {
  fs.copyFileSync(
    path.join(source, relativePath),
    path.join(destination, relativePath),
  );
}
fs.mkdirSync(path.join(destination, "images"), { recursive: true });
fs.copyFileSync(webConfig, path.join(destination, "web.config"));

const sourceText = fs.readFileSync(path.join(source, "data.js"), "utf8");
const context = {};
vm.createContext(context);
vm.runInContext(`${sourceText}\nthis.__ideaData = ideaData;`, context, {
  filename: "data.js",
  timeout: 5000,
});
if (!Array.isArray(context.__ideaData)) {
  throw new Error("data.js did not define an ideaData array.");
}

const ideas = context.__ideaData.filter(
  (idea) => idea && idea.title && idea.title !== "New Idea",
);
const ids = new Set();
const missingImages = [];
for (const idea of ideas) {
  const id = String(idea.id || "");
  if (!id || ids.has(id)) {
    throw new Error(`Missing or duplicate idea id: ${id || "(empty)"}`);
  }
  ids.add(id);
  const images =
    Array.isArray(idea.images) && idea.images.length
      ? idea.images
      : [idea.image].filter(Boolean);
  if (!images.length) {
    missingImages.push(`${id}: no image path`);
    continue;
  }
  for (const image of images) {
    const relativeImage = String(image)
      .split(/[?#]/, 1)[0]
      .replaceAll("/", path.sep);
    if (!fs.existsSync(path.join(source, relativeImage))) {
      missingImages.push(`${id}: ${image}`);
    }
  }
}
if (missingImages.length) {
  throw new Error(
    `Referenced images are missing:\n${missingImages.slice(0, 20).join("\n")}`,
  );
}

fs.writeFileSync(
  path.join(destination, "data.json"),
  `${JSON.stringify(ideas, null, 2)}\n`,
  "utf8",
);
process.stdout.write(`Prepared ${ideas.length} Interiorgram ideas.\n`);
