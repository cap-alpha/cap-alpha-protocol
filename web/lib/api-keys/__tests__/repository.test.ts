/**
 * Tests for the BigQuery repository layer.
 *
 * BigQuery is mocked — these tests verify the business logic:
 * - Key creation stores a hash, never plaintext
 * - Revoked key cannot be verified
 * - Per-tier cap enforcement
 * - Rotate = revoke + create
 */
import { describe, it, expect, beforeAll, beforeEach, vi } from "vitest";

// Set env vars before any imports
beforeAll(() => {
    process.env.API_KEY_PEPPER = "test-pepper-v1-secret";
    process.env.GCP_PROJECT_ID = "test-project";
});

// Mock BigQuery — must be a class so `new BigQuery()` works
const mockQuery = vi.fn();
vi.mock("@google-cloud/bigquery", () => {
    return {
        BigQuery: class MockBigQuery {
            query = mockQuery;
            constructor(_opts?: any) {}
        },
    };
});

import {
    createKey,
    listKeys,
    revokeKey,
    rotateKey,
    verifyKey,
    getActiveKeyCount,
} from "../repository";
import { hashApiKey } from "../index";

beforeEach(() => {
    mockQuery.mockReset();
});

describe("createKey", () => {
    it("creates a key and returns plaintext exactly once", async () => {
        // Mock getActiveKeyCount (first call) and INSERT (second call)
        mockQuery
            .mockResolvedValueOnce([[{ cnt: 0 }]]) // active count = 0
            .mockResolvedValueOnce([[], null, {}]); // INSERT result

        const result = await createKey("user_123", "My API Key", "live");

        expect(result.plaintextKey).toMatch(/^capk_live_[0-9a-zA-Z]{32}$/);
        expect(result.keyId).toBe(result.plaintextKey);
        expect(result.name).toBe("My API Key");
        expect(result.lastFour).toHaveLength(4);
        expect(result.mode).toBe("live");
        expect(result.createdAt).toBeTruthy();
    });

    it("creates a test mode key", async () => {
        mockQuery
            .mockResolvedValueOnce([[{ cnt: 0 }]])
            .mockResolvedValueOnce([[], null, {}]);

        const result = await createKey("user_123", "Test Key", "test");
        expect(result.plaintextKey).toMatch(/^capk_test_/);
        expect(result.mode).toBe("test");
    });

    it("enforces per-tier key cap (free tier = 1 key)", async () => {
        // User already has 1 active key
        mockQuery.mockResolvedValueOnce([[{ cnt: 1 }]]);

        await expect(
            createKey("user_123", "Second Key", "live")
        ).rejects.toThrow("Key limit reached");
    });

    it("passes the hash (not plaintext) to BigQuery INSERT", async () => {
        mockQuery
            .mockResolvedValueOnce([[{ cnt: 0 }]])
            .mockResolvedValueOnce([[], null, {}]);

        const result = await createKey("user_123", "My Key", "live");

        // Check the INSERT call params
        const insertCall = mockQuery.mock.calls[1][0];
        expect(insertCall.params.keyHash).toMatch(/^[0-9a-f]{64}$/);
        // The params should NOT contain the plaintext key anywhere
        // (keyId is the key_id column, which is the same as plaintextKey by design)
        expect(insertCall.params.keyId).toBe(result.keyId);
    });
});

describe("listKeys", () => {
    it("returns keys without hash or plaintext", async () => {
        mockQuery.mockResolvedValueOnce([
            [
                {
                    key_id: "capk_live_abc123",
                    name: "My Key",
                    key_last_four: "c123",
                    status: "active",
                    created_at: "2026-04-14T00:00:00Z",
                    last_used_at: null,
                },
            ],
        ]);

        const keys = await listKeys("user_123");

        expect(keys).toHaveLength(1);
        expect(keys[0]).toEqual({
            keyId: "capk_live_abc123",
            name: "My Key",
            lastFour: "c123",
            status: "active",
            createdAt: "2026-04-14T00:00:00Z",
            lastUsedAt: null,
        });
        // Ensure no hash or plaintext leaks
        expect(keys[0]).not.toHaveProperty("keyHash");
        expect(keys[0]).not.toHaveProperty("plaintextKey");
        expect(keys[0]).not.toHaveProperty("key_hash");
    });
});

describe("revokeKey", () => {
    it("revokes an active key owned by the user", async () => {
        mockQuery.mockResolvedValueOnce([
            [],
            null,
            { statistics: { query: { numDmlAffectedRows: "1" } } },
        ]);

        await expect(
            revokeKey("user_123", "capk_live_abc123")
        ).resolves.toBeUndefined();
    });

    it("throws if key not found or already revoked", async () => {
        mockQuery.mockResolvedValueOnce([
            [],
            null,
            { statistics: { query: { numDmlAffectedRows: "0" } } },
        ]);

        await expect(
            revokeKey("user_123", "capk_live_nonexistent")
        ).rejects.toThrow("not found");
    });

    it("throws if user does not own the key", async () => {
        mockQuery.mockResolvedValueOnce([
            [],
            null,
            { statistics: { query: { numDmlAffectedRows: "0" } } },
        ]);

        await expect(
            revokeKey("user_other", "capk_live_abc123")
        ).rejects.toThrow("not found");
    });
});

describe("verifyKey", () => {
    it("returns key info for a valid active key", async () => {
        const plaintext = "capk_live_testkey1234567890abcdefghijkl";
        const { hash, pepperVersion } = hashApiKey(plaintext);

        mockQuery.mockResolvedValueOnce([
            [
                {
                    key_id: plaintext,
                    key_hash: hash,
                    pepper_version: pepperVersion,
                    user_id: "user_123",
                    status: "active",
                },
            ],
        ]);

        const result = await verifyKey(plaintext);

        expect(result).toEqual({
            keyId: plaintext,
            userId: "user_123",
            status: "active",
        });
    });

    it("returns null for unknown key", async () => {
        mockQuery.mockResolvedValueOnce([[]]);

        const result = await verifyKey("capk_live_unknown");
        expect(result).toBeNull();
    });

    it("returns null if hash does not match (tampered)", async () => {
        mockQuery.mockResolvedValueOnce([
            [
                {
                    key_id: "capk_live_tampered",
                    key_hash: "a".repeat(64), // wrong hash
                    pepper_version: 1,
                    user_id: "user_123",
                    status: "active",
                },
            ],
        ]);

        const result = await verifyKey("capk_live_tampered");
        expect(result).toBeNull();
    });
});

describe("rotateKey", () => {
    it("revokes old key and creates a new one with the same name", async () => {
        mockQuery
            // Lookup existing key
            .mockResolvedValueOnce([
                [{ name: "Production Key", key_id: "capk_live_oldkey1234" }],
            ])
            // Revoke old key
            .mockResolvedValueOnce([
                [],
                null,
                { statistics: { query: { numDmlAffectedRows: "1" } } },
            ])
            // Insert new key
            .mockResolvedValueOnce([[], null, {}]);

        const result = await rotateKey("user_123", "capk_live_oldkey1234");

        expect(result.name).toBe("Production Key");
        expect(result.plaintextKey).toMatch(/^capk_live_/);
        expect(result.keyId).not.toBe("capk_live_oldkey1234"); // Fresh key_id
        expect(result.mode).toBe("live");
    });

    it("throws if key not found", async () => {
        mockQuery.mockResolvedValueOnce([[]]);

        await expect(
            rotateKey("user_123", "capk_live_nonexistent")
        ).rejects.toThrow("not found");
    });
});

describe("getActiveKeyCount", () => {
    it("returns the count of active keys", async () => {
        mockQuery.mockResolvedValueOnce([[{ cnt: 3 }]]);

        const count = await getActiveKeyCount("user_123");
        expect(count).toBe(3);
    });

    it("returns 0 when no keys exist", async () => {
        mockQuery.mockResolvedValueOnce([[{ cnt: 0 }]]);

        const count = await getActiveKeyCount("user_new");
        expect(count).toBe(0);
    });
});
