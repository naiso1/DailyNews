"use strict";

// Authentication belongs to the existing interior DB. Edition activity IDs and
// subscription rows stay in their original DBs; never use an identity ID as an
// exterior activity user ID.
const fs = require("node:fs");
const path = require("node:path");
const { DatabaseSync } = require("node:sqlite");

function databasePaths(identityDbFile, exteriorDbFile) {
  for (const file of [identityDbFile, exteriorDbFile]) {
    if (!file || !path.isAbsolute(file) || !fs.statSync(file).isFile()) {
      throw new Error("Shared identity requires two existing absolute database paths.");
    }
  }
  const interior = fs.realpathSync(identityDbFile);
  const exterior = fs.realpathSync(exteriorDbFile);
  if (interior.toLowerCase() === exterior.toLowerCase()) throw new Error("Edition databases must be separate.");
  return { interior, exterior };
}

function connect(paths, readOnly = false) {
  const db = new DatabaseSync(paths.interior, { readOnly });
  db.exec("PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;");
  db.prepare("ATTACH DATABASE ? AS exterior").run(paths.exterior);
  return db;
}

function transaction(db, work) {
  db.exec("BEGIN IMMEDIATE");
  try {
    const result = work();
    db.exec("COMMIT");
    return result;
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }
}

function audit(db) {
  const interior = db.prepare("SELECT * FROM main.users ORDER BY id").all();
  const exterior = db.prepare("SELECT * FROM exterior.users ORDER BY id").all();
  for (const rows of [interior, exterior]) {
    const emails = new Set();
    for (const user of rows) {
      const normalized = user.email.trim().toLowerCase();
      if (normalized !== user.email || emails.has(normalized)) {
        throw new Error("Normalize duplicate or noncanonical account emails before migration.");
      }
      emails.add(normalized);
    }
  }
  const known = new Set(interior.map((user) => user.email));
  return {
    interior, exterior,
    report: {
      interiorAccounts: interior.length, exteriorAccounts: exterior.length,
      exteriorOnlyAccounts: exterior.filter((user) => !known.has(user.email)).length,
      overlappingAccounts: exterior.filter((user) => known.has(user.email)).length,
      interiorRecipients: db.prepare("SELECT COUNT(*) AS n FROM main.mail_subscriptions WHERE enabled=1").get().n,
      exteriorRecipients: db.prepare("SELECT COUNT(*) AS n FROM exterior.mail_subscriptions WHERE enabled=1").get().n,
    },
  };
}

function migrate(identityDbFile, exteriorDbFile, apply = false) {
  const paths = databasePaths(identityDbFile, exteriorDbFile);
  const db = connect(paths, !apply);
  try {
    const { interior, exterior, report } = audit(db);
    if (!apply) return { ...report, applied: false };
    const marker = db.prepare("SELECT setting_value FROM settings WHERE setting_key='shared_identity_v1'").get();
    if (marker) {
      if (marker.setting_value !== paths.exterior) throw new Error("Existing shared identity points to a different exterior DB.");
      return { ...report, applied: true, alreadyMigrated: true };
    }
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const backups = [];
    for (const [schema, file] of [["main", paths.interior], ["exterior", paths.exterior]]) {
      const backup = `${file}.before-shared-identity-${stamp}.bak`;
      db.prepare(`VACUUM ${schema} INTO ?`).run(backup);
      backups.push(backup);
    }
    transaction(db, () => {
      const find = db.prepare("SELECT id FROM main.users WHERE email=?");
      const insert = db.prepare("INSERT INTO main.users(email,display_name,password_hash,password_salt,email_verified,is_admin,created_at,updated_at) VALUES(?,?,?,?,?,0,?,?)");
      const subscription = db.prepare("INSERT OR IGNORE INTO main.mail_subscriptions(email,display_name,user_id,enabled,source) VALUES(?,?,?,?,'registered_user')");
      // Missing rows are not evidence of consent. Keep every existing enabled
      // value, and prevent the legacy startup seed from enabling missing rows.
      for (const user of interior) subscription.run(user.email, user.display_name, user.id, 0);
      for (const user of exterior) {
        let identity = find.get(user.email);
        if (!identity) {
          const result = insert.run(user.email, user.display_name, user.password_hash, user.password_salt,
            user.email_verified, user.created_at, user.updated_at);
          identity = { id: Number(result.lastInsertRowid) };
          // Importing an exterior account must never subscribe it to interior mail.
          subscription.run(user.email, user.display_name, identity.id, 0);
        }
      }
      // Old exterior sessions must not authenticate an overlapping interior account.
      db.exec("DELETE FROM exterior.sessions");
      db.prepare("INSERT INTO settings(setting_key,setting_value) VALUES('shared_identity_v1',?)").run(paths.exterior);
    });
    const after = audit(db).report;
    if (after.interiorRecipients !== report.interiorRecipients || after.exteriorRecipients !== report.exteriorRecipients) {
      throw new Error("Subscriptions changed unexpectedly.");
    }
    return { ...after, applied: true, backups, preservedInteriorSessions: true };
  } finally { db.close(); }
}

function openSharedIdentity({ identityDbFile, exteriorDbFile, edition, localDbFile }) {
  const paths = databasePaths(identityDbFile, exteriorDbFile);
  const expectedLocal = edition === "interior" ? paths.interior : paths.exterior;
  if (fs.realpathSync(localDbFile).toLowerCase() !== expectedLocal.toLowerCase()) {
    throw new Error("Shared identity edition DB does not match this server root.");
  }
  const db = connect(paths);
  const marker = db.prepare("SELECT setting_value FROM settings WHERE setting_key='shared_identity_v1'").get();
  if (!marker || marker.setting_value !== paths.exterior) {
    db.close();
    throw new Error("Run the reviewed shared identity migration before enabling the server.");
  }
  const schema = (id) => id === "interior" ? "main" : "exterior";
  const byEmail = db.prepare("SELECT * FROM main.users WHERE email=?");
  const byId = db.prepare("SELECT * FROM main.users WHERE id=?");
  function localUser(identity, target = edition) {
    if (target === "interior") return identity;
    let local = db.prepare("SELECT * FROM exterior.users WHERE email=?").get(identity.email);
    if (!local) {
      db.prepare("INSERT OR IGNORE INTO exterior.users(email,display_name,password_hash,password_salt,email_verified,is_admin) VALUES(?,?,'!','!',?,?)")
        .run(identity.email, identity.display_name, identity.email_verified, identity.is_admin);
      local = db.prepare("SELECT * FROM exterior.users WHERE email=?").get(identity.email);
    }
    if (local.display_name !== identity.display_name || local.is_admin !== identity.is_admin) {
      db.prepare("UPDATE exterior.users SET display_name=?,is_admin=?,updated_at=CURRENT_TIMESTAMP WHERE id=?")
        .run(identity.display_name, identity.is_admin, local.id);
      db.prepare("UPDATE exterior.comments SET user_name=? WHERE user_id=?").run(identity.display_name, local.id);
      local = db.prepare("SELECT * FROM exterior.users WHERE id=?").get(local.id);
    }
    return local;
  }
  function subscriptions(email) {
    return Object.fromEntries(["interior", "exterior"].map((id) => [id,
      Boolean(db.prepare(`SELECT enabled FROM ${schema(id)}.mail_subscriptions WHERE email=?`).get(email)?.enabled)]));
  }
  function writeSubscription(identity, target, enabled, overwrite) {
    const user = localUser(identity, target);
    db.prepare(`INSERT INTO ${schema(target)}.mail_subscriptions(email,display_name,user_id,enabled,source)
      VALUES(?,?,?,?,'registered_user') ON CONFLICT(email) DO UPDATE SET display_name=excluded.display_name,
      user_id=excluded.user_id,source='registered_user',updated_at=CURRENT_TIMESTAMP${overwrite ? ",enabled=excluded.enabled" : ""}`)
      .run(identity.email, identity.display_name, user.id, enabled ? 1 : 0);
  }
  return {
    byEmail: (email) => byEmail.get(email), byId: (id) => byId.get(id), localUser, subscriptions,
    register({ email, displayName, hash, salt, isAdmin, choices }) {
      return transaction(db, () => {
        db.prepare("INSERT INTO main.users(email,display_name,password_hash,password_salt,is_admin) VALUES(?,?,?,?,?)")
          .run(email, displayName, hash, salt, isAdmin ? 1 : 0);
        const identity = byEmail.get(email);
        for (const target of ["interior", "exterior"]) {
          const explicit = typeof choices[target] === "boolean";
          writeSubscription(identity, target, explicit ? choices[target] : edition === "interior" && target === "interior", explicit);
        }
        return identity;
      });
    },
    setSubscriptions(identityId, choices, expectedSubscriptions) {
      return transaction(db, () => {
        const identity = byId.get(identityId);
        if (expectedSubscriptions) {
          const current = subscriptions(identity.email);
          if (["interior", "exterior"].some((target) => current[target] !== expectedSubscriptions[target])) {
            const error = new Error("Subscription settings changed. Reload the current choices before saving.");
            error.code = "subscription_conflict";
            throw error;
          }
        }
        for (const target of ["interior", "exterior"]) {
          if (typeof choices[target] === "boolean") writeSubscription(identity, target, choices[target], true);
        }
        return subscriptions(identity.email);
      });
    },
    profile(identityId, displayName) {
      return transaction(db, () => {
        db.prepare("UPDATE main.users SET display_name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?").run(displayName, identityId);
        const identity = byId.get(identityId);
        for (const target of ["interior", "exterior"]) {
          const local = localUser(identity, target);
          db.prepare(`UPDATE ${schema(target)}.comments SET user_name=? WHERE user_id=?`).run(displayName, local.id);
          db.prepare(`UPDATE ${schema(target)}.mail_subscriptions SET display_name=? WHERE email=?`).run(displayName, identity.email);
        }
        return identity;
      });
    },
    changePassword(identityId, hash, salt) {
      transaction(db, () => {
        db.prepare("UPDATE main.users SET password_hash=?,password_salt=?,updated_at=CURRENT_TIMESTAMP WHERE id=?").run(hash, salt, identityId);
        db.prepare("DELETE FROM main.sessions WHERE user_id=?").run(identityId);
      });
    },
    sessionUser(hash, now) {
      return db.prepare("SELECT u.* FROM main.sessions s JOIN main.users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?").get(hash, now);
    },
    touchSession(hash) { db.prepare("UPDATE main.sessions SET last_seen_at=CURRENT_TIMESTAMP WHERE token_hash=?").run(hash); },
    deleteSession(hash) { db.prepare("DELETE FROM main.sessions WHERE token_hash=?").run(hash); },
    createSession(hash, userId, expiresAt) {
      db.prepare("DELETE FROM main.sessions WHERE expires_at<=?").run(new Date().toISOString());
      db.prepare("INSERT INTO main.sessions(token_hash,user_id,expires_at) VALUES(?,?,?)").run(hash, userId, expiresAt);
    },
    close() { db.close(); },
  };
}

module.exports = { migrate, openSharedIdentity };
