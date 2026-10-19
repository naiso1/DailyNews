"use strict";
// Named usage details arrive only from the administrator-protected API.
window.renderDailyNewsWeeklyReports = async (container, request) => {
  if (!container) return;
  container.style.cssText = 'min-width:0;scroll-margin-top:80px';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const percent = (value,total) => total ? Math.round(100*value/total) : 0;
  container.innerHTML = '<p class="account-note">各室の週次利用レポートを読み込み中...</p>';
  let reports;
  try { reports = (await request('/admin/weekly-reports')).reports || []; }
  catch (_) { container.innerHTML = '<p class="account-note">週次レポートを読み込めませんでした。管理画面を開き直してください。</p>'; return; }
  if (!reports.length) { container.innerHTML = '<p class="account-note">週次レポートは準備中です。</p>'; return; }
  let week = reports.find(report=>report.complete)?.week || reports[0].week;
  let edition = window.DAILYNEWS_CONFIG?.id === 'exterior' ? 'exterior' : 'interior';
  const labels = {interior:'内装開発室（内装版の利用）',exterior:'外装開発室（外装版の利用）'};
  const rooms = {interior:'内装開発室',exterior:'外装開発室'};
  const bar = (active,total) => `<div role="img" aria-label="利用率${percent(active,total)}%" style="min-width:90px;height:9px;background:#25374c;border-radius:5px;overflow:hidden"><div style="width:${percent(active,total)}%;height:100%;background:#74c9b1"></div></div>`;
  const rowFor = report => report.rooms?.[edition] || (()=>{const row=report.rows.find(r=>r.level==='room'&&r.name===rooms[edition]);return row?{...row,...row.editions[edition]}:null;})();
  const trend = () => {
    const weeks=reports.slice().reverse(), x=i=>45+i*550/Math.max(1,weeks.length-1), y=v=>155-v*1.15;
    const values=weeks.map(r=>{const row=rowFor(r);return row?percent(row.active,row.headcount):null;});
    return `<div style="overflow:auto"><svg viewBox="0 0 640 205" role="img" aria-label="${esc(labels[edition])}の週次利用率" style="width:100%;min-width:380px">${[0,50,100].map(n=>`<line x1="45" x2="595" y1="${y(n)}" y2="${y(n)}" stroke="#344257"/><text x="4" y="${y(n)+4}" fill="#c2ccdc" font-size="12">${n}%</text>`).join('')}<polyline points="${values.map((v,i)=>v===null?'':`${x(i)},${y(v)}`).join(' ')}" fill="none" stroke="#74c9b1" stroke-width="2"/>${values.map((v,i)=>v===null?'':`<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="#74c9b1"><title>${esc(weeks[i].week)}：${v}%</title></circle><text x="${x(i)}" y="${y(v)-9}" text-anchor="middle" fill="#c2ccdc" font-size="12">${v}%</text>`).join('')}${weeks.map((r,i)=>`<text x="${x(i)}" y="183" text-anchor="middle" fill="#c2ccdc" font-size="11">${esc(r.week.slice(5))}${r.complete?'':'*'}</text>`).join('')}</svg></div><p class="account-note">* は途中の週。9月28日の週は10月1日以降の部分計測です。</p>`;
  };
  const draw = () => {
    const report=reports.find(r=>r.week===week), section=report.rooms?.[edition];
    const controls=`<h3 class="account-section-title">各室のデイリーニュース利用状況</h3><div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px"><label>対象週 <select data-week>${reports.map(r=>`<option value="${esc(r.week)}" ${r.week===week?'selected':''}>${esc(r.week)}〜${esc(r.end)}${r.complete?'':'（途中）'}</option>`).join('')}</select></label><label>対象室・版 <select data-edition>${Object.entries(labels).map(([key,label])=>`<option value="${key}" ${key===edition?'selected':''}>${label}</option>`).join('')}</select></label></div>`;
    const bind=()=>{container.querySelector('[data-week]').addEventListener('change',e=>{week=e.target.value;draw();});container.querySelector('[data-edition]').addEventListener('change',e=>{edition=e.target.value;draw();});};
    if(!section){container.innerHTML=controls+'<p class="account-note">この週の氏名付き室別レポートを準備中です。</p>';bind();return;}
    const c=report.coverage[edition], before=!c.readsStarted||c.readsStarted>report.end;
    const read=m=>before?'計測前':`${m.reads}回${c.readsComplete?'':' ※'}`;
    const readNote=before?'記事閲覧数はこの週にはまだ計測していません。「計測前」と表示します。':!c.readsComplete?`※ 記事閲覧数は${esc(c.readsStarted)}の計測開始後の記録です。この印は閲覧数だけに付き、利用日数・いいね・コメントには付きません。`:'';
    const noteHtml=readNote?`<p class="account-note" style="padding:10px;border-left:3px solid #8ba7c8;background:#1b2a3b">${readNote}</p>`:'';
    const memberRow=m=>`<tr${m.active?'':' style="background:#3b301b;color:#fff0ce"'}><td>${m.active?esc(m.name):`<strong>${esc(m.name)}</strong><br><span style="font-size:12px;font-weight:bold;color:#ffdb8f">フォロー対象</span>`}</td><td>${esc(m.status)}</td><td>${m.days}日</td><td>${esc(m.lastActivity||'—')}</td><td>${read(m)}</td><td>${m.likes}件</td><td>${m.comments}件</td></tr>`;
    const inactive=section.registeredInactive+section.unregistered;
    container.innerHTML=controls+`
      ${Date.now()-new Date(reports[0].generatedAt).getTime()>36*3600000?'<p class="account-note">集計更新から36時間以上経過しています。前回の結果です。</p>':''}
      <h4>${esc(section.room)}：${esc(section.title)}</h4>
      <div style="display:flex;gap:18px;flex-wrap:wrap;margin:16px 0"><div><strong style="font-size:24px">${percent(section.active,section.headcount)}%</strong><br>利用 ${section.active} / ${section.headcount}人</div><div><strong style="font-size:24px">${section.registeredInactive}人</strong><br>登録済・利用記録なし</div><div><strong style="font-size:24px">${section.unregistered}人</strong><br>未登録</div></div>
      <p class="account-note">利用率＝自室の版を利用したメンバー数 ÷ その室の名簿人数。名簿は${esc(report.masterDate)}時点、登録状態は対象週末時点です。</p>
      ${!section.usageComplete?'<p class="account-note">この週は利用の部分計測です。利用記録がなくても、計測開始前に利用していた可能性があります。</p>':''}
      ${noteHtml}
      <div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>グループ</th><th>利用 / 名簿人数</th><th>利用率</th><th>利用記録なし</th><th>記事閲覧</th><th>いいね</th><th>コメント</th></tr></thead><tbody>${section.groups.map(g=>`<tr><td>${esc(g.label)}</td><td>${g.active}/${g.headcount}人</td><td>${percent(g.active,g.headcount)}%${bar(g.active,g.headcount)}</td><td>${g.registeredInactive+g.unregistered}人</td><td>${read(g)}</td><td>${g.likes}件</td><td>${g.comments}件</td></tr>`).join('')}</tbody></table></div>
      <h4>フォロー対象の確認（利用記録なし ${inactive}人）</h4>
      <p class="account-note">未登録の方には登録案内、登録済みで利用記録がない方にはアクセス方法や利用しづらい点の確認にお使いください。</p>
      ${section.groups.map(g=>`<p><b>${esc(g.label)}</b>：${g.members.filter(m=>!m.active).map(m=>`${esc(m.name)}（${esc(m.status)}）`).join('、')||'利用記録なしの人はいません。'}</p>`).join('')}
      <h4>グループごとの個人別利用状況</h4>
      <p class="account-note">背景色・太字・「フォロー対象」は、対象週の利用記録がない方です。利用日数は、自室の版でログインした画面利用・記事閲覧・いいね・コメントのいずれかを記録した日数です。同じ日は1日と数えます。</p>
      ${noteHtml}
      ${section.groups.map(g=>`<details open style="margin-bottom:16px"><summary>${esc(g.label)}（${g.active}/${g.headcount}人が利用）</summary><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>氏名</th><th>対象週の状態</th><th>利用日数</th><th>週内の最終利用</th><th>記事閲覧</th><th>いいね</th><th>コメント</th></tr></thead><tbody>${g.members.map(memberRow).join('')}</tbody></table></div></details>`).join('')}
      <p class="account-note">利用記録なしは対象週に利用を確認できない状態です。未ログインの閲覧は個人に割り当てていません。</p>
      <details open><summary>週ごとの利用率（${esc(labels[edition])}）</summary>${trend()}</details>
      <details><summary>集計方法</summary><ul class="account-note"><li>ログインした画面利用・記事閲覧・いいね・コメントのいずれかで利用ありとします。同じ人は1人、同じ日は1日です。</li><li>いいね・コメントは対象週に作成され、集計時点で残っている件数です。</li><li>個人別の利用状況は管理者だけが閲覧できます。週次メールは承認済みの管理者宛てに配信します。</li><li>完了した週の所属と利用状況は保存した値を表示します。途中の週は日次更新します。</li><li>集計：${esc(new Date(report.roomDetailsGeneratedAt||report.generatedAt).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}))} JST</li></ul></details>`;
    bind();
  };
  draw();
};
