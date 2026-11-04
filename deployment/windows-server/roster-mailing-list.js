"use strict";

// Private, edition-local enrollment ledger. Never create accounts or override choices.
function syncRoster(db, payload, edition, {dryRun = false} = {}) {
  const room = {interior: "内装開発室", exterior: "外装開発室"}[edition];
  const today = new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);
  if (!room || payload?.schema !== 1 || payload.edition !== edition ||
      !/^\d{4}-\d{2}-\d{2}$/.test(payload.masterDate || "") || payload.masterDate > today ||
      !/^[a-f0-9]{64}$/.test(payload.masterHash || "") ||
      !Number.isInteger(payload.memberCount) || payload.memberCount < 1 ||
      !Array.isArray(payload.recipients) || payload.recipients.length > payload.memberCount) {
    throw new Error("Invalid employee master envelope");
  }
  const emails = new Set();
  for (const row of payload.recipients) {
    if (typeof row?.email !== "string" || row.email !== row.email.normalize("NFKC").trim().toLowerCase() ||
        row.email.length > 254 || !/^[^\s@;<>]+@(?:[a-z0-9-]+\.)*toyoda-gosei\.co\.jp$/.test(row.email) ||
        row.room !== room || typeof row.displayName !== "string" || emails.has(row.email)) {
      throw new Error("Invalid employee master recipient");
    }
    emails.add(row.email);
  }
  db.exec("BEGIN IMMEDIATE");
  try {
    db.exec(`CREATE TABLE IF NOT EXISTS roster_mail_enrollment (
      email TEXT PRIMARY KEY, master_date TEXT NOT NULL, master_hash TEXT NOT NULL,
      outcome TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS roster_mail_state (
      id INTEGER PRIMARY KEY CHECK(id=1), master_date TEXT NOT NULL, master_hash TEXT NOT NULL,
      member_count INTEGER NOT NULL, room_count INTEGER NOT NULL,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );`);
    const previous = db.prepare("SELECT * FROM roster_mail_state WHERE id=1").get();
    if (previous && (payload.masterDate < previous.master_date ||
        Math.abs(payload.memberCount - previous.member_count) > Math.max(5, previous.member_count * .2) ||
        Math.abs(payload.recipients.length - previous.room_count) > Math.max(5, previous.room_count * .2))) {
      throw new Error("Employee master moved backwards or changed substantially; enrollment held");
    }
    const result = {status: dryRun ? "preview" : "success", masterDate: payload.masterDate,
      supplied: payload.recipients.length, added: 0, enabledExisting: 0, disabledExisting: 0, previouslySeen: 0};
    const seen = db.prepare("SELECT 1 FROM roster_mail_enrollment WHERE email=?");
    const subscription = db.prepare("SELECT enabled FROM mail_subscriptions WHERE email=?");
    const user = db.prepare("SELECT id FROM users WHERE email=?");
    const insert = db.prepare("INSERT INTO mail_subscriptions(email,display_name,user_id,enabled,source) VALUES(?,?,?,1,?)");
    const record = db.prepare("INSERT OR IGNORE INTO roster_mail_enrollment(email,master_date,master_hash,outcome) VALUES(?,?,?,?)");
    for (const row of payload.recipients) {
      const existing = subscription.get(row.email);
      let outcome;
      if (existing) {
        outcome = existing.enabled ? "enabledExisting" : "disabledExisting";
      } else if (seen.get(row.email)) {
        // Explicit deletion after enrollment must not subscribe this person again.
        outcome = "previouslySeen";
      } else {
        const account = user.get(row.email);
        insert.run(row.email, row.displayName.slice(0, 40) || null, account?.id ?? null,
          account ? "registered_user" : "manual");
        outcome = "added";
      }
      result[outcome]++;
      record.run(row.email, payload.masterDate, payload.masterHash, outcome);
    }
    db.prepare(`INSERT INTO roster_mail_state(id,master_date,master_hash,member_count,room_count) VALUES(1,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET master_date=excluded.master_date,master_hash=excluded.master_hash,
      member_count=excluded.member_count,room_count=excluded.room_count,updated_at=CURRENT_TIMESTAMP`)
      .run(payload.masterDate, payload.masterHash, payload.memberCount, payload.recipients.length);
    db.exec(dryRun ? "ROLLBACK" : "COMMIT");
    return result;
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }
}

module.exports = {syncRoster};
