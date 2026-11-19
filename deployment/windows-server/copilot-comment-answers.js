'use strict';
// Public answers are separate from human comments and reaction/ranking counts.
const crypto = require('node:crypto');
const mention = text => /(?:^|\s)@copilot(?=$|[\s、,:：?？])/i.test(text || '');
const hash = text => crypto.createHash('sha256').update(text).digest('hex');
const fail = code => Object.assign(new Error(code), {safeCode: code});
function createStore({db, readJob, intervalMs = 5000}) {
  db.exec(`CREATE TABLE IF NOT EXISTS copilot_comment_answers (
    comment_id INTEGER PRIMARY KEY REFERENCES comments(id) ON DELETE CASCADE,
    owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_hash TEXT NOT NULL, job_id TEXT, status TEXT NOT NULL DEFAULT 'waiting',
    answer TEXT, completed_at TEXT, next_poll_at INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
  );`);
  const find = db.prepare('SELECT * FROM copilot_comment_answers WHERE comment_id=?');
  const comment = db.prepare('SELECT * FROM comments WHERE id=? AND item_id=?');
  let closed = false, busy = false;
  function owned(user, itemId, commentId) {
    if (!/^(jp|us|eu|cn|in|paper)\d+$/.test(itemId || '') || !Number.isSafeInteger(commentId)) throw fail('INVALID_REQUEST');
    const c = comment.get(commentId, itemId);
    if (!c || Number(c.user_id) !== Number(user.id)) throw fail('NOT_FOUND');
    return c;
  }
  function consent(user, itemId, commentId) {
    const c = owned(user, itemId, commentId);
    db.prepare(`INSERT OR IGNORE INTO copilot_comment_answers
      (comment_id,owner_user_id,question_hash,created_at,updated_at) VALUES(?,?,?,?,?)`)
      .run(c.id, user.id, hash(c.comment_text), Date.now(), Date.now());
  }
  function publicAnswer(commentId) {
    const row = find.get(commentId);
    return row ? {status:row.status, ...(row.status === 'published' ? {answer:row.answer,completedAt:row.completed_at} : {})} : null;
  }
  function record(user, job) {
    if (closed || !job || job.scope || !/^[a-f0-9]{64}$/.test(job.id || '')) return null;
    const row = find.get(job.commentId);
    if (!row || Number(row.owner_user_id) !== Number(user.id)) return null;
    const c = owned(user, job.itemId, job.commentId);
    if (row.question_hash !== hash(c.comment_text)) throw fail('STALE_QUESTION');
    if (row.job_id && row.job_id !== job.id) throw fail('STALE_QUESTION');
    if (row.status === 'published') return publicAnswer(c.id);
    const done = job.status === 'done' && typeof job.answer === 'string' && job.answer.trim() && job.answer.length <= 10000;
    const status = done ? 'published' : ['error','needs_review','done'].includes(job.status) ? 'unavailable' : 'pending';
    const completed = Number.isFinite(Date.parse(job.completedAt)) ? new Date(job.completedAt).toISOString() : new Date().toISOString();
    db.prepare(`UPDATE copilot_comment_answers SET job_id=?,status=?,answer=?,completed_at=?,next_poll_at=?,updated_at=? WHERE comment_id=?`)
      .run(job.id, status, done ? job.answer.trim() : null, done ? completed : null, Date.now()+intervalMs, Date.now(), c.id);
    return publicAnswer(c.id);
  }
  function publish(user, job) {
    if (!job || job.scope || job.status !== 'done' || !job.answer?.trim() || job.answer.length > 10000 || !/^[a-f0-9]{64}$/.test(job.id || '')) throw fail('INVALID_REQUEST');
    owned(user, job.itemId, job.commentId);
    consent(user, job.itemId, job.commentId);
    return record(user, job);
  }
  function failed(user, itemId, commentId) {
    const row=find.get(commentId);if(!row||Number(row.owner_user_id)!==Number(user.id))return;
    owned(user,itemId,commentId);
    db.prepare("UPDATE copilot_comment_answers SET status='unavailable',updated_at=? WHERE comment_id=? AND status!='published'").run(Date.now(),commentId);
  }
  async function poll() {
    if (closed || busy) return;
    busy = true;
    try {
      const rows = db.prepare(`SELECT a.*,u.email,c.item_id FROM copilot_comment_answers a
        JOIN users u ON u.id=a.owner_user_id JOIN comments c ON c.id=a.comment_id
        WHERE a.status='pending' AND a.next_poll_at<=? ORDER BY a.next_poll_at LIMIT 4`).all(Date.now());
      for (const row of rows) {
        if (closed) break;
        if (Date.now()-row.created_at > 86400000) {
          db.prepare("UPDATE copilot_comment_answers SET status='unavailable' WHERE comment_id=?").run(row.comment_id);continue;
        }
        try {
          const user = {id:Number(row.owner_user_id),email:row.email};
          const job = await readJob(user, row.job_id);
          if (closed) break;
          // A deleted comment or changed job is never recreated by a delayed result.
          if (job?.id !== row.job_id || job?.commentId !== row.comment_id || job?.itemId !== row.item_id) throw fail('NOT_FOUND');
          record(user, job);
        } catch {
          if (!closed) db.prepare('UPDATE copilot_comment_answers SET next_poll_at=? WHERE comment_id=?').run(Date.now()+60000,row.comment_id);
        }
      }
    } finally {busy=false;}
  }
  const timer = setInterval(()=>void poll(), intervalMs);timer.unref();
  return {consent,record,publish,failed,publicAnswer,poll,close(){closed=true;clearInterval(timer);}};
}
module.exports={createStore,mention};
