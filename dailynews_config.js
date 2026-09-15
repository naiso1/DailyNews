"use strict";

// Static preview fallback. The server supplies these settings from DAILYNEWS_EDITION.
(() => {
  const exterior = /^\/exterior(?:\/|$)/.test(location.pathname);
  window.DAILYNEWS_CONFIG = window.DAILYNEWS_CONFIG || {
    id: exterior ? "exterior" : "interior",
    name: exterior ? "外装製品デイリーニュース" : "内装製品デイリーニュース",
    basePath: exterior ? "/exterior" : "",
    apiBase: exterior ? "/exterior/api" : "/api",
    allowGuestRead: exterior,
    imageGenerationEnabled: !exterior,
  };
})();
