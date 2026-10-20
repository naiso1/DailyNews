"use strict";

// The original header stays in the HTML. Set dailynews-header-style to classic
// to restore it without reverting news, interaction data, or other UI changes.
(() => {
  if (document.querySelector('meta[name="dailynews-header-style"]')?.content !== "visual") return;
  if (!document.getElementById("dailyNewsHeaderStyles")?.sheet) return;
  const header = document.querySelector("header#top");
  if (!header || header.classList.contains("header-visual")) return;
  const brand = header.querySelector(".header-brand");
  const title = brand?.querySelector("h1");
  const actions = header.querySelector(".header-top-actions");
  const lead = header.querySelector(".lead");
  const editions = header.querySelector(".edition-links");
  const updated = header.querySelector(".header-update-status");
  const counter = header.querySelector(".compact-access-counter");
  if (![brand, title, actions, lead, editions, updated, counter].every(Boolean)) return;

  const exterior = window.DAILYNEWS_CONFIG?.id === "exterior";
  const productName = exterior ? "外装製品" : "内装製品";
  const utility = document.createElement("div");
  utility.className = "header-visual-utility";
  const department = document.createElement("div");
  department.className = "header-visual-department";
  department.innerHTML = 'IE開発部<span aria-hidden="true"></span><small>DAILY NEWS</small>';
  utility.append(department, actions);
  const resourceLinks = brand.querySelector(".header-resource-links") || brand.querySelector(".interiorgram-link");
  if (resourceLinks) actions.prepend(resourceLinks);

  const mainTitle = document.createElement("span");
  mainTitle.className = "header-title-main";
  mainTitle.textContent = productName;
  const subTitle = document.createElement("span");
  subTitle.className = "header-title-sub";
  subTitle.textContent = "デイリーニュース";
  title.replaceChildren(mainTitle, subTitle);
  // Keep the country-icon target available to the existing filter logic.
  const icon = brand.querySelector("#titleIcon");
  if (icon) icon.hidden = true;
  lead.textContent = `自動車${exterior ? "外装" : "内装"}の技術・製品・市場をひとつに。`;
  brand.append(lead);
  const hero = document.createElement("div");
  hero.className = "header-visual-hero";
  const signature = document.createElement("div");
  signature.className = "header-visual-signature";
  signature.setAttribute("aria-hidden", "true");
  signature.innerHTML = '<span>Daily perspectives.</span><small>TECHNOLOGY / PRODUCT / MARKET</small>';
  hero.append(brand, signature);

  const footer = document.createElement("div");
  footer.className = "header-visual-footer";
  const status = document.createElement("div");
  status.className = "header-visual-status";
  status.append(updated, counter);
  footer.append(editions, status);
  // Move existing controls instead of cloning them so their IDs and listeners survive.
  header.replaceChildren(utility, hero, footer);
  header.classList.add("header-visual");
})();
