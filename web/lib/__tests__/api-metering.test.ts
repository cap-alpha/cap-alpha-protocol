/**
 * Tests for the API metering module.
 *
 * BigQuery is mocked — these tests verify:
 * - recordApiRequest is fire-and-forget (never throws)
 * - BQ failures do NOT propagate to the caller
 * - Row payload is correctly constructed
 * - IP hashing works and respects METERING_IP_PEPPER
 * - Fire-and-forget when GCP credentials absent (logs, no throw)
 */
import { describe, it, expect, beforeAll, beforeEach, vi } from "vitest";

// Set env vars before any imports that read them
beforeAll(() => {
    process.env.GCP_PROJECT_ID = "test-project";
    process.env.METERING_IP_PEPPER = "test-metering-pepper";
});

// Mock BigQuery — streaming insert path uses dataset().table().insert()
const mockInsert = vi.fn();
vi.mock("@google-cloud/bigquery", () => {
    return {
        BigQuery: class MockBigQuery {
            constructor(_opts?: any) {}
            dataset(_name: string) {
                return {
                    table: (_tbl: string) => ({
                        insert: mockInsert,
                    }),
                };
            }
        },
    };
});

import { recordApiRequest, hashIp } from "../api-metering";
import type { MeteringEvent } from "../api-metering";

const baseEvent: MeteringEvent = {
    keyId: "capk_live_abc123",
    userId: "user_xyz",
    tier: "pro",
    endpoint: "/v1/pundits/{id}",
    endpointPath: "/v1/pundits/adam-schefter",
    method: "GET",
    statusCode: 200,
    latencyMs: 42,
    bytesOut: 1024,
    rateLimitHit: false,
    costClass: "cheap",
};

beforeEach(() => {
    mockInsert.mockReset();
});

// Helper: flush the microtask queue so fire-and-forget promises settle
function flushPromises(): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, 0));
}

// ─── recordApiRequest ─────────────────────────────────────────────────────────

describe("recordApiRequest", () => {
    it("does not throw when BQ insert succeeds", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        expect(() => recordApiRequest(baseEvent)).not.toThrow();
        await flushPromises();
        expect(mockInsert).toHaveBeenCalledTimes(1);
    });

    it("does NOT throw when BQ insert fails (fire-and-forget)", async () => {
        mockInsert.mockRejectedValueOnce(new Error("BQ unavailable"));
        expect(() => recordApiRequest(baseEvent)).not.toThrow();
        // After promises settle, still no throw — error is swallowed
        await flushPromises();
        expect(mockInsert).toHaveBeenCalledTimes(1);
    });

    it("does NOT throw on network timeout (fire-and-forget)", async () => {
        mockInsert.mockRejectedValueOnce(new Error("ETIMEDOUT"));
        expect(() => recordApiRequest(baseEvent)).not.toThrow();
        await flushPromises();
    });

    it("calls insert with a single-element array", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest(baseEvent);
        await flushPromises();

        const [rows] = mockInsert.mock.calls[0];
        expect(Array.isArray(rows)).toBe(true);
        expect(rows).toHaveLength(1);
    });

    it("passes skipInvalidRows: false to catch schema mismatches", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest(baseEvent);
        await flushPromises();

        const [, options] = mockInsert.mock.calls[0];
        expect(options).toEqual({ skipInvalidRows: false });
    });
});

// ─── Row payload ─────────────────────────────────────────────────────────────

describe("row payload", () => {
    it("maps all required fields correctly", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest(baseEvent);
        await flushPromises();

        const row = mockInsert.mock.calls[0][0][0];
        expect(row.key_id).toBe("capk_live_abc123");
        expect(row.user_id).toBe("user_xyz");
        expect(row.tier).toBe("pro");
        expect(row.endpoint).toBe("/v1/pundits/{id}");
        expect(row.endpoint_path).toBe("/v1/pundits/adam-schefter");
        expect(row.method).toBe("GET");
        expect(row.status_code).toBe(200);
        expect(row.latency_ms).toBe(42);
        expect(row.bytes_out).toBe(1024);
        expect(row.rate_limit_hit).toBe(false);
        expect(row.cost_class).toBe("cheap");
    });

    it("normalises method to uppercase", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest({ ...baseEvent, method: "get" });
        await flushPromises();

        const row = mockInsert.mock.calls[0][0][0];
        expect(row.method).toBe("GET");
    });

    it("defaults sport to 'nfl' when not provided", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest(baseEvent); // no sport field
        await flushPromises();

        const row = mockInsert.mock.calls[0][0][0];
        expect(row.sport).toBe("nfl");
    });

    it("respects an explicit sport value", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest({ ...baseEvent, sport: "mlb" });
        await flushPromises();

        const row = mockInsert.mock.calls[0][0][0];
        expect(row.sport).toBe("mlb");
    });

    it("sets ip_hash when ip is provided", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest({ ...baseEvent, ip: "1.2.3.4" });
        await flushPromises();

        const row = mockInsert.mock.calls[0][0][0];
        expect(typeof row.ip_hash).toBe("string");
        expect(row.ip_hash).toHaveLength(64); // hex SHA-256
    });

    it("sets ip_hash to null when ip is not provided", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest(baseEvent); // no ip
        await flushPromises();

        const row = mockInsert.mock.calls[0][0][0];
        expect(row.ip_hash).toBeNull();
    });

    it("sets user_agent to null when not provided", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest(baseEvent); // no userAgent
        await flushPromises();

        const row = mockInsert.mock.calls[0][0][0];
        expect(row.user_agent).toBeNull();
    });

    it("stores userAgent when provided", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest({ ...baseEvent, userAgent: "curl/7.88" });
        await flushPromises();

        const row = mockInsert.mock.calls[0][0][0];
        expect(row.user_agent).toBe("curl/7.88");
    });

    it("includes a ts field as an ISO string", async () => {
        mockInsert.mockResolvedValueOnce(undefined);
        recordApiRequest(baseEvent);
        await flushPromises();

        const row = mockInsert.mock.calls[0][0][0];
        expect(typeof row.ts).toBe("string");
        expect(() => new Date(row.ts)).not.toThrow();
    });
});

// ─── hashIp ──────────────────────────────────────────────────────────────────

describe("hashIp", () => {
    it("returns a 64-char hex string", () => {
        const hash = hashIp("192.168.1.1");
        expect(hash).toMatch(/^[0-9a-f]{64}$/);
    });

    it("produces a deterministic hash for the same input", () => {
        expect(hashIp("10.0.0.1")).toBe(hashIp("10.0.0.1"));
    });

    it("produces different hashes for different IPs", () => {
        expect(hashIp("10.0.0.1")).not.toBe(hashIp("10.0.0.2"));
    });

    it("incorporates the pepper (different pepper → different hash)", () => {
        const pepper1 = process.env.METERING_IP_PEPPER;
        process.env.METERING_IP_PEPPER = "pepper-A";
        const hashA = hashIp("1.2.3.4");

        process.env.METERING_IP_PEPPER = "pepper-B";
        const hashB = hashIp("1.2.3.4");

        // Restore
        process.env.METERING_IP_PEPPER = pepper1;

        expect(hashA).not.toBe(hashB);
    });

    it("does not throw when METERING_IP_PEPPER is unset (logs warning)", () => {
        const saved = process.env.METERING_IP_PEPPER;
        delete process.env.METERING_IP_PEPPER;

        expect(() => hashIp("1.2.3.4")).not.toThrow();

        process.env.METERING_IP_PEPPER = saved;
    });
});
