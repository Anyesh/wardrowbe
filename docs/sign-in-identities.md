# Sign-in identities

## Accounts and sign-in identities

An account holds at most one sign-in identity per provider (development login, OIDC, forward-auth). A new identity whose verified email belongs to an existing account with a verified email joins that account, and its sessions sit alongside the sessions of the account's other providers. A second identity from the same provider replaces the first, so two OIDC subjects, or two proxy usernames, that share an email address take turns holding the account and each sign-in ends the other's sessions.

To block a person, deactivate their account. Every request their tokens make is refused from then on. If the account's email is unverified, a sign-in whose provider verifies that address still gets a new account with it, so check `email_verified` too:

```sql
UPDATE users SET is_active = false WHERE email = 'person@example.com';
```

To unlink one sign-in identity and end its sessions, find the identity's id with `SELECT id, provider, subject FROM user_identities WHERE user_id = '<user id>';` and run the transaction below with it. It deletes the identity and clears the account's pre-upgrade sign-in when that names the identity (a forward-auth identity never does, even when a kept `legacy` identity has the same subject) or when the account keeps no other identity, so a later downgrade cannot hand the account back to an old sign-in. The id stays the same when a pre-upgrade (`legacy`) sign-in is used again after you listed it. The `DELETE` must report one row; zero means another sign-in replaced the identity in the meantime, so list the identities again.

```sql
BEGIN;
LOCK TABLE users, user_identities IN EXCLUSIVE MODE;
UPDATE users u SET external_id = NULL
FROM user_identities i
WHERE i.id = '<identity id>' AND u.id = i.user_id
  AND (
    (u.external_id = i.subject AND i.provider <> 'forward_auth')
    OR NOT EXISTS (SELECT 1 FROM user_identities o WHERE o.user_id = u.id AND o.id <> i.id)
  );
DELETE FROM user_identities WHERE id = '<identity id>';
COMMIT;
```

Unlinking does not block the person: while the account's email is verified, any later sign-in whose provider verifies that same address joins the account again. Deactivate the account for that.

## Upgrading to sign-in identities

This release keeps each user's sign-ins in a new `user_identities` table, one identity per provider, so signing in through a second provider no longer ends the first provider's sessions. The migration copies every user's existing sign-in into it.

### Repairing accounts if the migration ran while the old backend was still serving

If the migration ran while the old backend was still serving (the [upgrade steps](../README.md#upgrading) were not followed), two things can go wrong:

- Users the old backend created after the migration have no identity, so they can sign in only through a verified email address. An unverified one gets a conflict error, and a verified sign-in claiming the same address takes the address over and detaches the old account.
- Accounts the old backend linked to a new sign-in by email keep accepting the previous sign-in too.

This SQL repairs the accounts that existed before the backup, including one whose previous sign-in the new backend has already accepted since, and gives an identity to every account the old backend created without one. It holds sign-ins back until it commits. If another account still holds a sign-in it needs to restore, it changes nothing and names the accounts it could not repair; unlink the conflicting identity by hand (see [Accounts and sign-in identities](#accounts-and-sign-in-identities)) and run it again. Any other account the old backend linked to a new sign-in by email during the overlap (one created between the backup and the migration, or one the new backend created or linked) keeps the sign-ins it holds; the one the old backend linked gets the account back by signing in again with the same verified email, and an identity that should lose access has to be unlinked by hand (same section). Take the backup right before upgrading to keep that window short. Replace `<backup time>` with the time from the backup's file name, written as `2026-10-11T09:30:00`:

```sql
BEGIN;
LOCK TABLE users, user_identities IN EXCLUSIVE MODE;
-- Rows the migration copied keep the created_at of a user that existed before the backup; those
-- are the rows the old backend can have left stale by moving external_id.
CREATE TEMP TABLE stale ON COMMIT DROP AS
SELECT i.id, i.user_id FROM user_identities i JOIN users u ON u.id = i.user_id
WHERE i.provider IN ('legacy', 'oidc', 'dev') AND i.created_at = u.created_at
  AND u.created_at < TIMESTAMPTZ '<backup time>Z'
  AND u.external_id IS NOT NULL AND i.subject <> u.external_id;
CREATE TEMP TABLE targets ON COMMIT DROP AS
SELECT u.id FROM users u
WHERE u.external_id IS NOT NULL
  AND (
    u.id IN (SELECT user_id FROM stale)
    OR (
      u.created_at >= TIMESTAMPTZ '<backup time>Z'
      AND NOT EXISTS (SELECT 1 FROM user_identities i WHERE i.user_id = u.id)
    )
  );
DELETE FROM user_identities WHERE id IN (SELECT id FROM stale);
INSERT INTO user_identities (id, user_id, provider, subject, created_at)
SELECT gen_random_uuid(), u.id, 'legacy', u.external_id, u.created_at
FROM users u WHERE u.id IN (SELECT id FROM targets)
ON CONFLICT DO NOTHING;
DO $$
DECLARE skipped text;
BEGIN
  SELECT string_agg(u.email, ', ') INTO skipped FROM users u
  WHERE u.id IN (SELECT id FROM targets)
    AND (
      NOT EXISTS (SELECT 1 FROM user_identities i WHERE i.user_id = u.id
        AND i.subject = u.external_id AND i.provider IN ('legacy', 'oidc', 'dev'))
      OR EXISTS (SELECT 1 FROM user_identities i WHERE i.user_id <> u.id
        AND i.subject = u.external_id AND i.provider IN ('legacy', 'oidc', 'dev'))
    );
  IF skipped IS NOT NULL THEN
    RAISE EXCEPTION 'Nothing was changed. Another account holds the sign-in of: %', skipped;
  END IF;
END $$;
COMMIT;
```

### Downgrading below this migration

Downgrading below this migration keeps one sign-in per account (OIDC first, then development login, then the pre-upgrade one) and gives an account that loses every candidate a placeholder no sign-in matches. Forward-auth sign-ins are never kept, so an account whose only sign-in is forward-auth gets a placeholder. On the old version a verified sign-in whose email matches a placeholder account's verified email is linked to that account, while a matching unverified email moves to a new account and leaves the placeholder account's data behind. Every token issued after the upgrade stops working. Restore the backup instead where you can. To downgrade anyway, stop the backend and workers first, because the new backend answers every signed-in request with an error once the table is gone, and run the downgrade with the new image, since only it contains this migration:

```bash
docker compose stop backend worker image-worker
docker compose run --rm --no-deps backend alembic downgrade 6c1e8f2a9d47
```

Then point the image tags at the previous release and run `docker compose up -d`.

