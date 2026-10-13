"use strict";
// Reports contain aggregate counts only. The server enforces administrator access.
window.renderDailyNewsWeeklyReports = async (container, request) => {
  if (!container) return;
  container.style.cssText = 'min-width:0;scroll-margin-top:80px';
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  container.innerHTML = '<p class="account-note">グループ別の週次レポートを読み込み中...</p>';
  let reports;
  try { reports = (await request('/admin/weekly-reports')).reports || []; }
  catch (_) { container.innerHTML = '<p class="account-note">週次レポートを読み込めませんでした。管理画面を開き直してください。</p>'; return; }
  if (!reports.length) { container.innerHTML = '<p class="account-note">グループ別の週次レポートは準備中です。</p>'; return; }
  let week = reports.find(report => report.complete)?.week || reports[0].week;
  let edition = window.DAILYNEWS_CONFIG?.id || 'interior';
  let room = '';
  const labels = {interior:'内装版', exterior:'外装版', combined:'両版合計（人数の重複なし）'};
  const groupLabel = row => row.level === 'group' && ['内装開発室','外装開発室','IE開発部'].includes(row.name) ? row.name + '（グループ記載なし）' : row.name;
  const percent = (value, total) => total ? Math.round(100 * value / total) : 0;
  const trend = () => {
    const weeks = reports.slice().reverse();
    const names = room ? [room] : ['内装開発室','外装開発室','IE開発部 全体'];
    const colors = ['#72b8f0','#74c9b1','#c2a2ee'];
    const x = i => 50 + i * 560 / Math.max(1,weeks.length-1), y = value => 160-value*1.2;
    return `<div style="overflow:auto"><svg viewBox="0 0 660 230" role="img" aria-label="週ごとの利用率の折れ線グラフ" style="width:100%;min-width:480px">${[0,50,100].map(n=>`<line x1="50" x2="610" y1="${y(n)}" y2="${y(n)}" stroke="#344257"/><text x="8" y="${y(n)+4}" fill="#c2ccdc" font-size="12">${n}%</text>`).join('')}${names.map((name,n)=>{const values=weeks.map(r=>{const row=r.rows.find(v=>v.name===name&&v.level!=='group');return row?percent(row.editions[edition].active,row.headcount):null;});return `<polyline points="${values.map((v,i)=>v===null?'':`${x(i)},${y(v)}`).join(' ')}" fill="none" stroke="${colors[n]}" stroke-width="2"/>${values.map((v,i)=>v===null?'':`<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="${colors[n]}"><title>${esc(name)} ${esc(weeks[i].week)}：${v}%</title></circle>`).join('')}<text x="${50+n*195}" y="220" fill="${colors[n]}" font-size="12">${esc(name)}</text>`;}).join('')}${weeks.map((r,i)=>`<text x="${x(i)}" y="183" text-anchor="middle" fill="#c2ccdc" font-size="11">${esc(r.week.slice(5))}${r.complete?'':'*'}</text>`).join('')}</svg></div><p class="account-note">* は途中の週。2026-09-28の週は10月1日以降の部分計測です。表は横にスクロールできます。</p>`;
  };
  const draw = () => {
    const report = reports.find(row => row.week === week);
    const relevant = edition === 'combined' ? ['interior','exterior'] : [edition];
    const before = relevant.every(e => !report.coverage[e].readsStarted || report.coverage[e].readsStarted > report.end);
    const partial = relevant.some(e => !report.coverage[e].readsComplete);
    const usagePartial = relevant.some(e => !report.coverage[e].usageStarted || report.coverage[e].usageStarted > report.week);
    const read = m => before ? '計測前' : `${m.reads}回 / ${m.readsUsers}人${partial ? ' ※' : ''}`;
    const bar = (active, headcount) => `<div role="img" aria-label="利用率${percent(active,headcount)}%" style="min-width:100px;height:9px;background:#25374c;border-radius:5px;overflow:hidden"><div style="width:${percent(active,headcount)}%;height:100%;background:#74c9b1"></div></div>`;
    const total = report.rows[0];
    container.innerHTML = `<h3 class="account-section-title">グループ別の週次利用レポート</h3>
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px"><label>対象週 <select data-week>${reports.map(row => `<option value="${esc(row.week)}" ${row.week === week ? 'selected' : ''}>${esc(row.week)}〜${esc(row.end)}${row.complete ? '' : '（途中）'}</option>`).join('')}</select></label><label>利用する版 <select data-edition>${Object.entries(labels).map(([value,label])=>`<option value="${value}" ${value===edition?'selected':''}>${label}</option>`).join('')}</select></label><label>所属室 <select data-room>${['','内装開発室','外装開発室','IE開発部（室外）'].map(value=>`<option value="${value}" ${value===room?'selected':''}>${value||'全体'}</option>`).join('')}</select></label></div>
      ${Date.now()-new Date(reports[0].generatedAt).getTime()>36*3600000?'<p class="account-note">集計の更新から36時間以上経過しています。前回の結果を表示しています。</p>':''}
      <p class="account-note">名簿：${esc(report.masterDate)}時点・${total.headcount}人 ／ 共通アカウント登録：${total.registered}人（${percent(total.registered,total.headcount)}%）<br>集計：${esc(new Date(report.generatedAt).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}))} JST。所属と利用する版を分けて集計しています。</p>
      ${usagePartial ? '<p class="account-note">この週は利用人数の計測開始を含みます。開始前の利用は含まれません。</p>' : ''}
      <div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>所属</th><th>登録 / 名簿</th><th>利用人数・率</th><th>記事閲覧 / 人数</th><th>いいね / 人数</th><th>コメント / 人数</th></tr></thead><tbody>${report.rows.filter(row=>!room || row.level==='room'&&row.name===room || row.level==='group'&&(room==='IE開発部（室外）'?!row.name.startsWith('内装開発室')&&!row.name.startsWith('外装開発室'):row.name.startsWith(room))).map(row => { const m=row.editions[edition]; return `<tr style="${row.level==='group'?'':'font-weight:bold;background:rgba(111,167,255,.06)'}"><td>${esc(groupLabel(row))}</td><td>${row.registered}/${row.headcount}人</td><td>${m.active}人（${percent(m.active,row.headcount)}%）${bar(m.active,row.headcount)}</td><td>${read(m)}</td><td>${m.likes}件 / ${m.likesUsers}人</td><td>${m.comments}件 / ${m.commentsUsers}人</td></tr>`; }).join('')}</tbody></table></div>
      <p class="account-note">${before ? 'この週のグループ別閲覧数は計測前です。' : partial ? '※ 閲覧数は計測開始後の値です。週全体の数字ではありません。' : ''} 名簿外の利用者：${report.unmatched[edition].active}人（利用率に含めません）。</p>
      <details open><summary>週ごとの利用率の推移（${esc(labels[edition])}）</summary>${trend()}<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>週</th><th>内装開発室</th><th>外装開発室</th><th>IE開発部 全体</th></tr></thead><tbody>${reports.slice().reverse().map(r=>`<tr><td>${esc(r.week)}${r.complete?'':'（途中）'}</td>${['内装開発室','外装開発室','IE開発部 全体'].map(name=> { const row=r.rows.find(x=>x.name===name && x.level!=='group'); if(!row)return '<td>—</td>'; const active=row.editions[edition].active; return `<td>${active}/${row.headcount}人（${percent(active,row.headcount)}%）${bar(active,row.headcount)}</td>`; }).join('')}</tr>`).join('')}</tbody></table></div></details>
      <details><summary>集計方法・注意点</summary><ul class="account-note">${report.notes.map(note=>`<li>${esc(note)}</li>`).join('')}<li>完了した週のレポートは保存した値を表示します。途中の週は毎日の集計で更新します。</li></ul></details>`;
    container.querySelector('[data-week]').addEventListener('change', event => { week=event.target.value; draw(); });
    container.querySelector('[data-room]').addEventListener('change', event => { room=event.target.value; draw(); });
    container.querySelector('[data-edition]').addEventListener('change', event => { edition=event.target.value; draw(); });
  };
  draw();
};
