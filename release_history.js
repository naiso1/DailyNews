"use strict";

window.DAILYNEWS_RELEASE_HISTORY = [
  {
    date: "2026-08-28",
    title: "ブラウザの戻る・進む操作を改善",
    items: [
      "地域・ジャンル・日付・並び順・お気に入り表示の切り替え履歴を保存",
      "ブラウザの戻る・進むボタンで直前のニュース表示条件を復元",
    ],
  },
  {
    date: "2026-08-27",
    title: "マイページと管理機能を改善",
    items: [
      "ヘッダーから同期表示を外し、更新日時とシステムの説明を分かりやすく整理",
      "Newニュースを、コメント・いいねの反響を優先して表示する並び順に変更",
      "いいねボタンにマウスを重ねると、登録ユーザーの表示名を確認できるよう改善",
      "お気に入り・いいね・コメントを画像付きで、ニュースと企画アイデアに分けて表示",
      "登録状況と利用件数を確認できる中村管理者向け画面を追加",
      "サイト内で記事を開いた後に、元の検索・表示位置へ戻れるよう改善",
      "ニュース閲覧をユーザー登録・ログイン必須に変更し、更新履歴を追加",
    ],
  },
  {
    date: "2026-08-27",
    title: "ヘッダーをコンパクト化",
    items: ["タイトル・更新状況・アクセス数・マイページを2行に整理"],
  },
  {
    date: "2026-08-27",
    title: "ユーザーアカウントを追加",
    items: [
      "メールアドレスで登録し、端末をまたいでお気に入り・いいね・コメントを保存",
      "コメントの表示名変更とご意見ボックスを追加",
    ],
  },
  {
    date: "2026-07-29",
    title: "社内Webサーバーへ移行",
    items: ["公開先をGitHub PagesからIE台Webサーバーへ変更"],
  },
];

function escapeReleaseHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function initializeReleaseHistory() {
  if (document.documentElement.classList.contains("github-pages-migration")) return;
  const actions = document.querySelector(".header-top-actions");
  if (!actions || document.getElementById("releaseHistoryButton")) return;

  const style = document.createElement("style");
  style.textContent = `
    .release-history-button { min-height:36px; border:1px solid rgba(255,255,255,.13); border-radius:999px; padding:0 12px; background:rgba(255,255,255,.035); color:#cbd7e6; font-weight:700; white-space:nowrap; cursor:pointer; }
    .release-history-button:hover { border-color:rgba(111,167,255,.45); background:rgba(111,167,255,.1); }
    .release-history-overlay { position:fixed; inset:0; z-index:10030; display:none; align-items:center; justify-content:center; padding:18px; background:rgba(2,6,12,.8); backdrop-filter:blur(8px); }
    .release-history-overlay.open { display:flex; }
    .release-history-dialog { width:min(720px,100%); max-height:86vh; overflow:auto; border:1px solid rgba(111,167,255,.28); border-radius:20px; background:linear-gradient(145deg,#151f2c,#0c131f); color:#edf4fb; box-shadow:0 30px 90px rgba(0,0,0,.55); }
    .release-history-head { position:sticky; top:0; z-index:1; display:flex; align-items:center; justify-content:space-between; padding:17px 20px; border-bottom:1px solid rgba(255,255,255,.09); background:rgba(15,23,35,.97); }
    .release-history-head h2 { margin:0; font-size:19px; }
    .release-history-close { border:0; background:none; color:#c5cfdb; font-size:25px; cursor:pointer; }
    .release-history-list { display:grid; gap:0; padding:8px 20px 22px; }
    .release-history-entry { display:grid; grid-template-columns:96px minmax(0,1fr); gap:14px; padding:16px 0; border-bottom:1px solid rgba(255,255,255,.08); }
    .release-history-entry time { color:#7df1c2; font-size:12px; font-weight:800; }
    .release-history-entry h3 { margin:0 0 7px; font-size:15px; }
    .release-history-entry ul { margin:0; padding-left:18px; color:#aebcce; font-size:12px; line-height:1.75; }
    @media(max-width:560px) { .release-history-entry { grid-template-columns:1fr; gap:5px; } .release-history-button { min-height:34px; padding:0 10px; font-size:11px; } }
  `;
  document.head.appendChild(style);

  const button = document.createElement("button");
  button.id = "releaseHistoryButton";
  button.className = "release-history-button";
  button.type = "button";
  button.textContent = "更新履歴";
  actions.insertBefore(button, document.getElementById("accountHeaderSlot"));

  const overlay = document.createElement("div");
  overlay.className = "release-history-overlay";
  overlay.id = "releaseHistoryOverlay";
  overlay.innerHTML = `
    <section class="release-history-dialog" role="dialog" aria-modal="true" aria-labelledby="releaseHistoryTitle">
      <div class="release-history-head"><h2 id="releaseHistoryTitle">更新履歴</h2><button class="release-history-close" type="button" aria-label="閉じる">&times;</button></div>
      <div class="release-history-list">${window.DAILYNEWS_RELEASE_HISTORY.map((entry) => `
        <article class="release-history-entry">
          <time>${escapeReleaseHtml(entry.date)}</time>
          <div><h3>${escapeReleaseHtml(entry.title)}</h3><ul>${entry.items.map((item) => `<li>${escapeReleaseHtml(item)}</li>`).join("")}</ul></div>
        </article>`).join("")}</div>
    </section>`;
  document.body.appendChild(overlay);

  const close = () => {
    overlay.classList.remove("open");
    document.body.style.overflow = "";
  };
  button.addEventListener("click", () => {
    overlay.classList.add("open");
    document.body.style.overflow = "hidden";
  });
  overlay.querySelector(".release-history-close").addEventListener("click", close);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
}

document.addEventListener("DOMContentLoaded", initializeReleaseHistory);
