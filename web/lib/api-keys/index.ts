/**
 * API Key generation, hashing, and verification utilities.
 *
 * Key format: capk_{mode}_{32 chars base62}
 * Hash: SHA-256(pepper || plaintextKey)
 * Pepper is versioned so it can be rotated without mass invalidation.
 */
import { createHash, randomBytes } from "crypto";

// base62 alphabet: 0-9, a-z, A-Z
const BASE62_CHARS =
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

/**
 * Encode a Buffer into a base62 string of the desired length.
 * Uses rejection-free modular sampling from crypto-random bytes.
 */
export function base62Encode(buf: Buffer, length: number): string {
    let result = "";
    let i = 0;
    while (result.length < length) {
        // Wrap around if we run out of random bytes (shouldn't happen with 48 bytes for 32 chars)
        result += BASE62_CHARS[buf[i % buf.length] % 62];
        i++;
    }
    return result;
}

/** Current pepper version. Bump when rotating the pepper env var. */
const CURRENT_PEPPER_VERSION = 1;

function getPepper(version?: number): string {
    const pepper = process.env.API_KEY_PEPPER;
    if (!pepper) {
        throw new Error(
            "API_KEY_PEPPER environment variable is not set. Cannot hash API keys."
        );
    }
    // Future: support multiple pepper versions via a lookup map.
    // For now, only version 1 exists.
    if (version !== undefined && version !== CURRENT_PEPPER_VERSION) {
        throw new Error(
            `Unsupported pepper version: ${version}. Only version ${CURRENT_PEPPER_VERSION} is supported.`
        );
    }
    return pepper;
}

export type KeyMode = "live" | "test";

export interface GeneratedKey {
    /** Full key ID (same as the plaintext key): capk_{mode}_{32 base62 chars} */
    keyId: string;
    /** The full plaintext key — returned exactly once, never stored */
    plaintextKey: string;
    /** SHA-256(pepper || plaintextKey) */
    keyHash: string;
    /** The pepper version used for hashing */
    pepperVersion: number;
    /** Last 4 characters of the plaintext key for dashboard display */
    lastFour: string;
}

/**
 * Generate a new API key.
 *
 * @param mode - 'live' for production data, 'test' for sandbox dataset
 * @returns The generated key material. The plaintextKey must be shown to the
 *          user exactly once and never persisted.
 */
export function generateApiKey(mode: KeyMode): GeneratedKey {
    // 48 random bytes gives us plenty of entropy for 32 base62 chars
    const randomPart = base62Encode(randomBytes(48), 32);
    const plaintextKey = `capk_${mode}_${randomPart}`;
    const { hash, pepperVersion } = hashApiKey(plaintextKey);

    return {
        keyId: plaintextKey,
        plaintextKey,
        keyHash: hash,
        pepperVersion,
        lastFour: plaintextKey.slice(-4),
    };
}

/**
 * Hash a plaintext API key with the current pepper.
 *
 * @param plaintextKey - The full plaintext key
 * @returns The hex-encoded SHA-256 hash and pepper version
 */
export function hashApiKey(plaintextKey: string): {
    hash: string;
    pepperVersion: number;
} {
    const pepper = getPepper();
    const hash = createHash("sha256")
        .update(pepper + plaintextKey)
        .digest("hex");
    return { hash, pepperVersion: CURRENT_PEPPER_VERSION };
}

/**
 * Verify a plaintext key against a stored hash.
 *
 * Uses the stored pepper version to recompute the hash, enabling
 * pepper rotation without breaking existing keys.
 *
 * @param plaintextKey - The full plaintext key from the request
 * @param storedHash - The stored SHA-256 hash
 * @param storedPepperVersion - The pepper version used when the key was created
 * @returns true if the key matches
 */
export function verifyApiKey(
    plaintextKey: string,
    storedHash: string,
    storedPepperVersion: number
): boolean {
    const pepper = getPepper(storedPepperVersion);
    const computedHash = createHash("sha256")
        .update(pepper + plaintextKey)
        .digest("hex");

    // Constant-time comparison to prevent timing attacks
    if (computedHash.length !== storedHash.length) {
        return false;
    }
    let mismatch = 0;
    for (let i = 0; i < computedHash.length; i++) {
        mismatch |= computedHash.charCodeAt(i) ^ storedHash.charCodeAt(i);
    }
    return mismatch === 0;
}

/**
 * Parse a key prefix to determine the mode.
 * Returns null if the key doesn't match the expected format.
 */
export function parseKeyMode(plaintextKey: string): KeyMode | null {
    if (plaintextKey.startsWith("capk_live_")) return "live";
    if (plaintextKey.startsWith("capk_test_")) return "test";
    return null;
}
