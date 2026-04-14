/**
 * Tests for API key generation, hashing, and verification.
 *
 * These tests cover the pure crypto/utility layer — no BigQuery required.
 */
import { describe, it, expect, beforeAll, vi } from "vitest";

// Set the pepper env var before importing the module
beforeAll(() => {
    process.env.API_KEY_PEPPER = "test-pepper-v1-secret";
});

import {
    generateApiKey,
    hashApiKey,
    verifyApiKey,
    parseKeyMode,
    base62Encode,
} from "../index";

describe("base62Encode", () => {
    it("produces only alphanumeric characters", () => {
        const buf = Buffer.from("abcdefghijklmnopqrstuvwxyz0123456789ABCDEF");
        const encoded = base62Encode(buf, 32);
        expect(encoded).toMatch(/^[0-9a-zA-Z]+$/);
        expect(encoded).toHaveLength(32);
    });

    it("produces deterministic output for the same input", () => {
        const buf = Buffer.from("test-input-buffer-for-determinism");
        const a = base62Encode(buf, 16);
        const b = base62Encode(buf, 16);
        expect(a).toBe(b);
    });
});

describe("generateApiKey", () => {
    it("generates a live key with the correct prefix", () => {
        const key = generateApiKey("live");
        expect(key.plaintextKey).toMatch(/^capk_live_[0-9a-zA-Z]{32}$/);
        expect(key.keyId).toBe(key.plaintextKey);
    });

    it("generates a test key with the correct prefix", () => {
        const key = generateApiKey("test");
        expect(key.plaintextKey).toMatch(/^capk_test_[0-9a-zA-Z]{32}$/);
        expect(key.keyId).toBe(key.plaintextKey);
    });

    it("keyId equals plaintextKey", () => {
        const key = generateApiKey("live");
        expect(key.keyId).toBe(key.plaintextKey);
    });

    it("lastFour is the last 4 characters of the plaintext key", () => {
        const key = generateApiKey("live");
        expect(key.lastFour).toBe(key.plaintextKey.slice(-4));
        expect(key.lastFour).toHaveLength(4);
    });

    it("includes pepper version", () => {
        const key = generateApiKey("live");
        expect(key.pepperVersion).toBe(1);
    });

    it("generates unique keys", () => {
        const keys = new Set<string>();
        for (let i = 0; i < 100; i++) {
            keys.add(generateApiKey("live").plaintextKey);
        }
        expect(keys.size).toBe(100);
    });

    it("key hash is a valid 64-char hex string (SHA-256)", () => {
        const key = generateApiKey("live");
        expect(key.keyHash).toMatch(/^[0-9a-f]{64}$/);
    });
});

describe("hashApiKey", () => {
    it("returns a deterministic hash", () => {
        const key = "capk_live_abcdefghijklmnopqrstuvwxyz012345";
        const h1 = hashApiKey(key);
        const h2 = hashApiKey(key);
        expect(h1.hash).toBe(h2.hash);
    });

    it("returns a 64-char hex string", () => {
        const { hash } = hashApiKey("capk_live_test1234");
        expect(hash).toMatch(/^[0-9a-f]{64}$/);
    });

    it("different keys produce different hashes", () => {
        const h1 = hashApiKey("capk_live_key1key1key1key1key1key1key1key1").hash;
        const h2 = hashApiKey("capk_live_key2key2key2key2key2key2key2key2").hash;
        expect(h1).not.toBe(h2);
    });

    it("includes pepper version 1", () => {
        const { pepperVersion } = hashApiKey("capk_live_anything");
        expect(pepperVersion).toBe(1);
    });

    it("throws if API_KEY_PEPPER is not set", () => {
        const original = process.env.API_KEY_PEPPER;
        delete process.env.API_KEY_PEPPER;

        // Need to re-import to test without the pepper — but since the module
        // reads the env at call time, we can just test directly
        const { createHash } = require("crypto");
        // Actually, hashApiKey reads env.API_KEY_PEPPER at call time
        expect(() => hashApiKey("capk_live_test")).toThrow("API_KEY_PEPPER");

        process.env.API_KEY_PEPPER = original;
    });
});

describe("verifyApiKey", () => {
    it("returns true for a correct key", () => {
        const key = generateApiKey("live");
        const result = verifyApiKey(
            key.plaintextKey,
            key.keyHash,
            key.pepperVersion
        );
        expect(result).toBe(true);
    });

    it("returns false for a wrong key", () => {
        const key = generateApiKey("live");
        const result = verifyApiKey(
            "capk_live_wrongkeywrongkeywrongkeywrongkey",
            key.keyHash,
            key.pepperVersion
        );
        expect(result).toBe(false);
    });

    it("returns false for a tampered hash", () => {
        const key = generateApiKey("live");
        const tamperedHash = "a".repeat(64);
        const result = verifyApiKey(
            key.plaintextKey,
            tamperedHash,
            key.pepperVersion
        );
        expect(result).toBe(false);
    });

    it("returns false for mismatched hash length", () => {
        const key = generateApiKey("live");
        const result = verifyApiKey(key.plaintextKey, "short", key.pepperVersion);
        expect(result).toBe(false);
    });

    it("throws for unsupported pepper version", () => {
        const key = generateApiKey("live");
        expect(() =>
            verifyApiKey(key.plaintextKey, key.keyHash, 999)
        ).toThrow("Unsupported pepper version");
    });
});

describe("parseKeyMode", () => {
    it("returns 'live' for live keys", () => {
        expect(parseKeyMode("capk_live_abc123")).toBe("live");
    });

    it("returns 'test' for test keys", () => {
        expect(parseKeyMode("capk_test_abc123")).toBe("test");
    });

    it("returns null for invalid prefixes", () => {
        expect(parseKeyMode("sk_live_abc123")).toBeNull();
        expect(parseKeyMode("capk_staging_abc123")).toBeNull();
        expect(parseKeyMode("")).toBeNull();
    });
});
