/**
 * BigQuery CRUD operations for API keys.
 *
 * This is the source-of-truth layer. A Redis cache layer (Upstash)
 * will wrap verifyKey() in a follow-up issue.
 */
import { BigQuery } from "@google-cloud/bigquery";

import {
    GeneratedKey,
    KeyMode,
    generateApiKey,
    hashApiKey,
    parseKeyMode,
    verifyApiKey as verifyApiKeyUtil,
} from "./index";
import { getUserTier, getMaxKeysForTier } from "./tiers";

const PROJECT_ID = process.env.GCP_PROJECT_ID || "cap-alpha-protocol";
const DATASET = "monetization";
const TABLE = "api_keys";
const FULL_TABLE = `\`${PROJECT_ID}.${DATASET}.${TABLE}\``;

function getBigQuery(): BigQuery {
    return new BigQuery({
        projectId: PROJECT_ID,
        credentials:
            process.env.GCP_CLIENT_EMAIL && process.env.GCP_PRIVATE_KEY
                ? {
                      client_email: process.env.GCP_CLIENT_EMAIL,
                      private_key: process.env.GCP_PRIVATE_KEY.replace(
                          /\\n/g,
                          "\n"
                      ),
                  }
                : undefined,
    });
}

/** Returned to the caller on key creation — includes the plaintext key exactly once */
export interface CreateKeyResult {
    keyId: string;
    plaintextKey: string;
    name: string;
    lastFour: string;
    mode: KeyMode;
    createdAt: string;
}

/** Returned when listing keys — never includes the hash or plaintext */
export interface KeyListItem {
    keyId: string;
    name: string;
    lastFour: string;
    status: "active" | "revoked";
    createdAt: string;
    lastUsedAt: string | null;
}

/** Internal row shape from BigQuery */
interface KeyRow {
    key_id: string;
    key_hash: string;
    pepper_version: number;
    key_last_four: string;
    user_id: string;
    scopes: string[] | null;
    status: string;
    name: string;
    created_at: { value: string };
    revoked_at: { value: string } | null;
    last_used_at: { value: string } | null;
    last_used_ip: string | null;
}

/**
 * Create a new API key for a user.
 *
 * Enforces per-tier key caps. Returns the plaintext key exactly once.
 * The plaintext key is never stored — only the hash.
 */
export async function createKey(
    userId: string,
    name: string,
    mode: KeyMode = "live"
): Promise<CreateKeyResult> {
    // Enforce per-tier key cap
    const tier = await getUserTier(userId);
    const maxKeys = getMaxKeysForTier(tier);
    const activeCount = await getActiveKeyCount(userId);

    if (activeCount >= maxKeys) {
        throw new Error(
            `Key limit reached. Your ${tier} plan allows ${maxKeys} active key(s). ` +
                `You currently have ${activeCount}. Revoke an existing key or upgrade your plan.`
        );
    }

    const generated: GeneratedKey = generateApiKey(mode);
    const now = new Date().toISOString();

    const bq = getBigQuery();
    const query = `
        INSERT INTO ${FULL_TABLE}
            (key_id, key_hash, pepper_version, key_last_four, user_id, scopes, status, name, created_at)
        VALUES
            (@keyId, @keyHash, @pepperVersion, @lastFour, @userId, @scopes, 'active', @name, @createdAt)
    `;

    await bq.query({
        query,
        params: {
            keyId: generated.keyId,
            keyHash: generated.keyHash,
            pepperVersion: generated.pepperVersion,
            lastFour: generated.lastFour,
            userId,
            scopes: [],
            name,
            createdAt: now,
        },
        types: {
            keyId: "STRING",
            keyHash: "STRING",
            pepperVersion: "INT64",
            lastFour: "STRING",
            userId: "STRING",
            scopes: ["STRING"],
            name: "STRING",
            createdAt: "TIMESTAMP",
        },
    });

    return {
        keyId: generated.keyId,
        plaintextKey: generated.plaintextKey,
        name,
        lastFour: generated.lastFour,
        mode,
        createdAt: now,
    };
}

/**
 * List all keys for a user. Never returns the hash or plaintext.
 */
export async function listKeys(userId: string): Promise<KeyListItem[]> {
    const bq = getBigQuery();
    const query = `
        SELECT
            key_id,
            name,
            key_last_four,
            status,
            FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', created_at) AS created_at,
            FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', last_used_at) AS last_used_at
        FROM ${FULL_TABLE}
        WHERE user_id = @userId
        ORDER BY created_at DESC
    `;

    const [rows] = await bq.query({
        query,
        params: { userId },
        types: { userId: "STRING" },
    });

    return (rows as any[]).map((row) => ({
        keyId: row.key_id,
        name: row.name,
        lastFour: row.key_last_four,
        status: row.status as "active" | "revoked",
        createdAt: row.created_at,
        lastUsedAt: row.last_used_at || null,
    }));
}

/**
 * Revoke a key. Sets status='revoked' and records revoked_at.
 * Only the key owner can revoke their key.
 */
export async function revokeKey(userId: string, keyId: string): Promise<void> {
    const bq = getBigQuery();
    const now = new Date().toISOString();

    const query = `
        UPDATE ${FULL_TABLE}
        SET status = 'revoked', revoked_at = @revokedAt
        WHERE key_id = @keyId AND user_id = @userId AND status = 'active'
    `;

    // BigQuery DML returns metadata in the third tuple element, but
    // @google-cloud/bigquery types only expose 2 elements. Cast to any.
    const result: any = await bq.query({
        query,
        params: { keyId, userId, revokedAt: now },
        types: {
            keyId: "STRING",
            userId: "STRING",
            revokedAt: "TIMESTAMP",
        },
    });

    const numDmlAffectedRows =
        result[2]?.statistics?.query?.numDmlAffectedRows;
    if (numDmlAffectedRows === "0" || numDmlAffectedRows === 0) {
        throw new Error(
            "Key not found, already revoked, or you do not own this key."
        );
    }
}

/**
 * Rotate a key: revoke the old one and create a new one with the same name.
 * The new key gets a fresh key_id. Returns the new plaintext key exactly once.
 */
export async function rotateKey(
    userId: string,
    keyId: string
): Promise<CreateKeyResult> {
    // Look up the existing key to get its name and determine mode
    const bq = getBigQuery();
    const lookupQuery = `
        SELECT name, key_id
        FROM ${FULL_TABLE}
        WHERE key_id = @keyId AND user_id = @userId AND status = 'active'
    `;

    const [rows] = await bq.query({
        query: lookupQuery,
        params: { keyId, userId },
        types: { keyId: "STRING", userId: "STRING" },
    });

    if (!rows || (rows as any[]).length === 0) {
        throw new Error(
            "Key not found, already revoked, or you do not own this key."
        );
    }

    const existingKey = (rows as any[])[0];
    const name = existingKey.name;

    // Determine mode from the key_id prefix
    const mode = parseKeyMode(keyId) || "live";

    // Revoke old key
    await revokeKey(userId, keyId);

    // Create new key with the same name (bypasses tier cap since we just revoked one)
    const generated: GeneratedKey = generateApiKey(mode);
    const now = new Date().toISOString();

    const insertQuery = `
        INSERT INTO ${FULL_TABLE}
            (key_id, key_hash, pepper_version, key_last_four, user_id, scopes, status, name, created_at)
        VALUES
            (@keyId, @keyHash, @pepperVersion, @lastFour, @userId, @scopes, 'active', @name, @createdAt)
    `;

    await bq.query({
        query: insertQuery,
        params: {
            keyId: generated.keyId,
            keyHash: generated.keyHash,
            pepperVersion: generated.pepperVersion,
            lastFour: generated.lastFour,
            userId,
            scopes: [],
            name,
            createdAt: now,
        },
        types: {
            keyId: "STRING",
            keyHash: "STRING",
            pepperVersion: "INT64",
            lastFour: "STRING",
            userId: "STRING",
            scopes: ["STRING"],
            name: "STRING",
            createdAt: "TIMESTAMP",
        },
    });

    return {
        keyId: generated.keyId,
        plaintextKey: generated.plaintextKey,
        name,
        lastFour: generated.lastFour,
        mode,
        createdAt: now,
    };
}

/**
 * Verify a plaintext API key against the BigQuery store.
 *
 * Returns the key row if valid and active, null otherwise.
 * This is the BigQuery path — a Redis cache layer will wrap this.
 */
export async function verifyKey(
    plaintextKey: string
): Promise<{ keyId: string; userId: string; status: string } | null> {
    const { hash } = hashApiKey(plaintextKey);
    const bq = getBigQuery();

    const query = `
        SELECT key_id, key_hash, pepper_version, user_id, status
        FROM ${FULL_TABLE}
        WHERE key_hash = @keyHash
        LIMIT 1
    `;

    const [rows] = await bq.query({
        query,
        params: { keyHash: hash },
        types: { keyHash: "STRING" },
    });

    if (!rows || (rows as any[]).length === 0) {
        return null;
    }

    const row = (rows as any[])[0];

    // Double-check with full verification (handles pepper version)
    const isValid = verifyApiKeyUtil(
        plaintextKey,
        row.key_hash,
        row.pepper_version
    );

    if (!isValid) {
        return null;
    }

    return {
        keyId: row.key_id,
        userId: row.user_id,
        status: row.status,
    };
}

/**
 * Get the number of active keys for a user.
 */
export async function getActiveKeyCount(userId: string): Promise<number> {
    const bq = getBigQuery();
    const query = `
        SELECT COUNT(*) AS cnt
        FROM ${FULL_TABLE}
        WHERE user_id = @userId AND status = 'active'
    `;

    const [rows] = await bq.query({
        query,
        params: { userId },
        types: { userId: "STRING" },
    });

    return Number((rows as any[])[0]?.cnt ?? 0);
}

/**
 * Update last_used_at and last_used_ip for a key.
 * Called on each successful API request (fire-and-forget is fine).
 */
export async function touchLastUsed(
    keyId: string,
    ip: string
): Promise<void> {
    const bq = getBigQuery();
    const now = new Date().toISOString();

    const query = `
        UPDATE ${FULL_TABLE}
        SET last_used_at = @lastUsedAt, last_used_ip = @ip
        WHERE key_id = @keyId
    `;

    await bq.query({
        query,
        params: { keyId, lastUsedAt: now, ip },
        types: {
            keyId: "STRING",
            lastUsedAt: "TIMESTAMP",
            ip: "STRING",
        },
    });
}
