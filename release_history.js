"use strict";

window.DAILYNEWS_RELEASE_HISTORY = [
  {
    date: "2026-09-04",
    title: "メール配信先の管理機能を追加",
    items: [
      "管理画面から朝8時メールの配信先を追加・停止・削除できる機能を追加",
      "新しくユーザー登録した方を更新案内メールの配信先へ自動追加",
      "既存のメール配信先と登録ユーザーを統合し、業務用OneDrive経由でPower Automateへ安全に連携",
      "ページ更新時は認証確認が完了してから画面を切り替え、ログイン案内のちらつきを解消",
    ],
  },
  {
    date: "2026-09-03",
    title: "情報源・コメント通知・ランキングを改善",
    items: [
      "ヘッダーから定期収集RSSと掲載媒体を検索・確認できる情報源一覧を追加",
      "コメントの@メンションと本人への通知に対応",
      "コメント入力欄で@を押すと登録ユーザー候補からメンションできるように改善",
      "コメント欄の縦・横スクロールをなくし、投稿をカード内にすべて表示",
      "みんなの動きでコメント全文と過去12件までを確認できる表示切替を追加",
      "本文に重なる記事マウスオーバー時のコメント吹き出しを廃止",
      "人気ニュース・論文ランキングに「1日（本日）」を追加し、標準期間に設定",
    ],
  },
  {
    date: "2026-09-02",
    title: "コメントの動きと通知を追加",
    items: [
      "新着ニュースの並びを変えず、コメントが付いた記事を「みんなの動き」に再表示",
      "自分への返信、参加した記事の新規コメント、コメントへのいいねをベルで通知",
      "マイページに参加した記事と返信・更新の一覧を追加し、過去記事へ戻りやすく改善",
      "コメントへの返信機能を追加し、記事ごとのやり取りを継続できるよう対応",
    ],
  },
  {
    date: "2026-09-02",
    title: "Webサーバーの保存容量を最適化",
    items: [
      "画像一式を含む古いデプロイ履歴54世代を整理し、約40.7GBの空き容量を確保",
      "公開中と直前のリリースを保護し、サイト表示や画像を維持したまま容量を削減",
      "今後の更新時は最新3世代だけを自動保持し、容量増加の再発を防止",
    ],
  },
  {
    date: "2026-09-02",
    title: "更新結果に応じたメール通知へ改善",
    items: [
      "ニュース更新処理の成功・失敗を自動判定し、実行結果をステータスとして記録・公開",
      "更新成功時のみ関係者へ完了メールを送り、失敗時は管理者だけへ通知するよう変更",
      "古い実行結果やステータス取得失敗も更新失敗として扱い、誤った完了通知を防止",
      "Power Automateから管理者宛てのテストメールを送信し、本番設定への自動復元まで確認",
    ],
  },
  {
    date: "2026-09-01",
    title: "コメント確認と関連度フィードバックを改善",
    items: [
      "記事にマウスを重ねると、投稿済みコメントを吹き出しで確認できるよう改善",
      "内装開発と関係ない記事を報告できる「関連なし」ボタンを追加",
      "関連なしの評価をユーザー別に保存し、今後の関連度判定改善に活用できるよう対応",
    ],
  },
  {
    date: "2026-09-01",
    title: "ニュースURLとサムネイルの誤結合を修正",
    items: [
      "Google Newsの転送先が正しく取得できなかった記事を公開対象から除外",
      "途中で切れたURLとGoogle Newsの共通画像を次回以降は自動で除外",
      "本日の考察・企画アイデアから無効なニュース参照を削除",
    ],
  },
  {
    date: "2026-08-31",
    title: "ニュースの並び替えを見やすく改善",
    items: [
      "New表示でいいねやコメントにより順位が変わる際、カードが新しい位置へ滑らかに移動するよう改善",
      "更新履歴を含む画面機能がブラウザに古く残らないよう、読み込み時のキャッシュ制御を改善",
    ],
  },
  {
    date: "2026-08-28",
    title: "初回案内とブラウザ操作を改善",
    items: [
      "未ログイン時に、ログイン方式へ変更した理由とTG社員向け登録案内を表示",
      "未登録の方と登録済みの方の入口を分け、登録方法を分かりやすく改善",
      "管理画面の登録日時・最終利用日時を日本時間（JST）で表示",
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
