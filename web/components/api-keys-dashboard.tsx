"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import {
    Key,
    Plus,
    Copy,
    RotateCcw,
    Trash2,
    AlertTriangle,
    Check,
    Loader2,
    Shield,
    Eye,
    EyeOff,
} from "lucide-react";

// ---------- Types ----------

interface ApiKey {
    keyId: string;
    name: string;
    lastFour: string;
    status: "active" | "revoked";
    mode?: "live" | "test";
    createdAt: string;
    lastUsedAt: string | null;
}

interface ApiKeysResponse {
    keys: ApiKey[];
    tier: string;
    maxKeys: number;
}

interface CreateKeyResponse {
    keyId: string;
    plaintextKey: string;
    lastFour: string;
    name: string;
    mode: string;
    createdAt: string;
}

// ---------- Helpers ----------

function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

function formatRelativeDate(dateStr: string | null): string {
    if (!dateStr) return "Never";
    const now = new Date();
    const date = new Date(dateStr);
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return formatDate(dateStr);
}

function tierLabel(tier: string): string {
    return tier.charAt(0).toUpperCase() + tier.slice(1);
}

function tierColor(tier: string): string {
    switch (tier) {
        case "pro":
            return "bg-accent-editorial/10 text-accent-editorial border-accent-editorial/30";
        case "api":
            return "bg-gold/10 text-gold border-gold/30";
        case "enterprise":
            return "bg-pending/10 text-pending border-pending/30";
        default:
            return "bg-editorial-border text-ink-2 border-editorial-border";
    }
}

// ---------- Sub-components ----------

function KeyRevealPanel({
    plaintextKey,
    onDone,
}: {
    plaintextKey: string;
    onDone: () => void;
}) {
    const [copied, setCopied] = useState(false);
    const [revealed, setRevealed] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(plaintextKey);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="space-y-4">
            <div className="rounded-lg border border-pending/30 bg-pending/10 p-4">
                <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle className="h-4 w-4 text-pending" />
                    <span className="text-sm font-medium text-pending">
                        This key will not be shown again. Copy it now.
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    <code className="flex-1 rounded-md bg-zinc-950 px-3 py-2.5 font-mono text-sm text-correct break-all select-all">
                        {revealed
                            ? plaintextKey
                            : plaintextKey.slice(0, 10) +
                              "\u2022".repeat(32) +
                              plaintextKey.slice(-4)}
                    </code>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setRevealed(!revealed)}
                        className="shrink-0"
                    >
                        {revealed ? (
                            <EyeOff className="h-4 w-4" />
                        ) : (
                            <Eye className="h-4 w-4" />
                        )}
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCopy}
                        className="shrink-0 gap-1.5"
                    >
                        {copied ? (
                            <>
                                <Check className="h-3.5 w-3.5 text-correct" />
                                Copied
                            </>
                        ) : (
                            <>
                                <Copy className="h-3.5 w-3.5" />
                                Copy
                            </>
                        )}
                    </Button>
                </div>
            </div>
            <DialogFooter>
                <Button onClick={onDone} className="w-full sm:w-auto">
                    Done
                </Button>
            </DialogFooter>
        </div>
    );
}

function SkeletonRows() {
    return (
        <>
            {[1, 2, 3].map((i) => (
                <TableRow key={i}>
                    <TableCell>
                        <div className="h-4 w-24 bg-editorial-border rounded animate-pulse" />
                    </TableCell>
                    <TableCell>
                        <div className="h-4 w-36 bg-editorial-border rounded animate-pulse" />
                    </TableCell>
                    <TableCell>
                        <div className="h-5 w-14 bg-editorial-border rounded-full animate-pulse" />
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                        <div className="h-4 w-20 bg-editorial-border rounded animate-pulse" />
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                        <div className="h-4 w-16 bg-editorial-border rounded animate-pulse" />
                    </TableCell>
                    <TableCell>
                        <div className="h-8 w-20 bg-editorial-border rounded animate-pulse" />
                    </TableCell>
                </TableRow>
            ))}
        </>
    );
}

// ---------- Main Component ----------

export function ApiKeysDashboard() {
    // State
    const [keys, setKeys] = useState<ApiKey[]>([]);
    const [tier, setTier] = useState("free");
    const [maxKeys, setMaxKeys] = useState(1);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [autoProvisionDone, setAutoProvisionDone] = useState(false);

    // Modal state
    const [createOpen, setCreateOpen] = useState(false);
    const [revokeOpen, setRevokeOpen] = useState(false);
    const [rotateOpen, setRotateOpen] = useState(false);
    const [revealKey, setRevealKey] = useState<string | null>(null);
    const [revealDialogOpen, setRevealDialogOpen] = useState(false);

    // Form state
    const [newKeyName, setNewKeyName] = useState("");
    const [newKeyMode, setNewKeyMode] = useState<"live" | "test">("live");
    const [creating, setCreating] = useState(false);
    const [revoking, setRevoking] = useState(false);
    const [rotating, setRotating] = useState(false);
    const [targetKey, setTargetKey] = useState<ApiKey | null>(null);

    // Fetch keys
    const fetchKeys = useCallback(async () => {
        try {
            const res = await fetch("/api/api-keys");
            if (!res.ok) throw new Error("Failed to fetch API keys");
            const data: ApiKeysResponse = await res.json();
            setKeys(data.keys);
            setTier(data.tier);
            setMaxKeys(data.maxKeys);
            return data;
        } catch (err) {
            setError(
                err instanceof Error ? err.message : "Failed to fetch keys"
            );
            return null;
        }
    }, []);

    // Auto-provision on first visit
    const autoProvision = useCallback(async () => {
        try {
            const res = await fetch("/api/api-keys", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: "Default Key",
                    mode: "live",
                }),
            });
            if (res.ok) {
                // We don't show the key reveal for auto-provisioned keys
                // since the user can always create a new one
                await fetchKeys();
            }
        } catch {
            // Silently fail auto-provision — user can create manually
        }
    }, [fetchKeys]);

    useEffect(() => {
        let mounted = true;
        (async () => {
            setLoading(true);
            const data = await fetchKeys();
            if (!mounted) return;

            // Auto-provision if no keys exist and this is first visit
            if (data && data.keys.length === 0 && !autoProvisionDone) {
                setAutoProvisionDone(true);
                await autoProvision();
            }
            setLoading(false);
        })();
        return () => {
            mounted = false;
        };
    }, [fetchKeys, autoProvision, autoProvisionDone]);

    // Create key
    const handleCreate = async () => {
        if (!newKeyName.trim()) return;
        setCreating(true);
        setError(null);
        try {
            const res = await fetch("/api/api-keys", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: newKeyName.trim(),
                    mode: newKeyMode,
                }),
            });
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.error || "Failed to create key");
            }
            const data: CreateKeyResponse = await res.json();
            setCreateOpen(false);
            setNewKeyName("");
            setNewKeyMode("live");

            // Show the plaintext key
            setRevealKey(data.plaintextKey);
            setRevealDialogOpen(true);

            // Refresh list
            await fetchKeys();
        } catch (err) {
            setError(
                err instanceof Error ? err.message : "Failed to create key"
            );
        } finally {
            setCreating(false);
        }
    };

    // Revoke key
    const handleRevoke = async () => {
        if (!targetKey) return;
        setRevoking(true);
        setError(null);
        try {
            const res = await fetch(`/api/api-keys/${targetKey.keyId}`, {
                method: "DELETE",
            });
            if (!res.ok) throw new Error("Failed to revoke key");
            setRevokeOpen(false);
            setTargetKey(null);
            await fetchKeys();
        } catch (err) {
            setError(
                err instanceof Error ? err.message : "Failed to revoke key"
            );
        } finally {
            setRevoking(false);
        }
    };

    // Rotate key
    const handleRotate = async () => {
        if (!targetKey) return;
        setRotating(true);
        setError(null);
        try {
            const res = await fetch(
                `/api/api-keys/${targetKey.keyId}/rotate`,
                {
                    method: "POST",
                }
            );
            if (!res.ok) throw new Error("Failed to rotate key");
            const data: CreateKeyResponse = await res.json();
            setRotateOpen(false);
            setTargetKey(null);

            // Show the new plaintext key
            setRevealKey(data.plaintextKey);
            setRevealDialogOpen(true);

            // Refresh list
            await fetchKeys();
        } catch (err) {
            setError(
                err instanceof Error ? err.message : "Failed to rotate key"
            );
        } finally {
            setRotating(false);
        }
    };

    const activeKeys = keys.filter((k) => k.status === "active");
    const atCap = activeKeys.length >= maxKeys;

    return (
        <TooltipProvider>
            <main className="min-h-[100dvh] bg-editorial-bg font-sans text-ink">
                {/* Header */}
                <div className="border-b border-editorial-border bg-editorial-card">
                    <div className="container mx-auto px-4 py-6 sm:px-6 lg:px-8">
                        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                            <div className="flex items-center gap-3">
                                <div className="rounded-lg bg-accent-editorial/10 border border-accent-editorial/30 p-2.5">
                                    <Key className="h-6 w-6 text-accent-editorial" />
                                </div>
                                <div>
                                    <h1 className="text-2xl font-bold tracking-tight">
                                        API Keys
                                    </h1>
                                    <p className="text-sm text-ink-2 mt-0.5">
                                        Manage your API keys for programmatic
                                        access to the Pundit Ledger.
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <Badge
                                    className={`${tierColor(tier)} text-xs px-2.5 py-1`}
                                >
                                    {tierLabel(tier)} tier
                                </Badge>
                                <span className="text-sm text-ink-2">
                                    {activeKeys.length} of {maxKeys} keys used
                                </span>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="container mx-auto px-4 py-8 sm:px-6 lg:px-8">
                    {/* Error banner */}
                    {error && (
                        <div className="mb-6 rounded-lg border border-incorrect/30 bg-incorrect/10 px-4 py-3 flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4 text-incorrect shrink-0" />
                            <p className="text-sm text-incorrect">{error}</p>
                            <button
                                onClick={() => setError(null)}
                                className="ml-auto text-incorrect hover:text-incorrect/80 text-sm"
                            >
                                Dismiss
                            </button>
                        </div>
                    )}

                    <Card className="bg-editorial-card border-editorial-border">
                        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-editorial-border pb-6">
                            <div>
                                <CardTitle className="text-lg">
                                    Your Keys
                                </CardTitle>
                                <CardDescription>
                                    Keys grant access to the Pundit Ledger API.
                                    Keep them secret.
                                </CardDescription>
                            </div>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div>
                                        <Button
                                            onClick={() => setCreateOpen(true)}
                                            disabled={atCap || loading}
                                            className="gap-2"
                                        >
                                            <Plus className="h-4 w-4" />
                                            Create New Key
                                        </Button>
                                    </div>
                                </TooltipTrigger>
                                {atCap && (
                                    <TooltipContent>
                                        <p>
                                            {tierLabel(tier)} tier limit reached
                                            ({maxKeys} key
                                            {maxKeys !== 1 ? "s" : ""})
                                        </p>
                                    </TooltipContent>
                                )}
                            </Tooltip>
                        </CardHeader>
                        <CardContent className="p-0">
                            {loading ? (
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Name</TableHead>
                                            <TableHead>Key</TableHead>
                                            <TableHead>Status</TableHead>
                                            <TableHead className="hidden sm:table-cell">
                                                Created
                                            </TableHead>
                                            <TableHead className="hidden md:table-cell">
                                                Last Used
                                            </TableHead>
                                            <TableHead className="text-right">
                                                Actions
                                            </TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        <SkeletonRows />
                                    </TableBody>
                                </Table>
                            ) : keys.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
                                    <Shield className="h-12 w-12 text-ink-3 mb-4" />
                                    <p className="text-lg font-medium text-ink-2">
                                        No API keys yet
                                    </p>
                                    <p className="text-sm text-ink-2 mt-1 mb-6">
                                        Create one to get started with the
                                        Pundit Ledger API.
                                    </p>
                                    <Button
                                        onClick={() => setCreateOpen(true)}
                                        className="gap-2"
                                    >
                                        <Plus className="h-4 w-4" />
                                        Create Your First Key
                                    </Button>
                                </div>
                            ) : (
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Name</TableHead>
                                            <TableHead>Key</TableHead>
                                            <TableHead>Status</TableHead>
                                            <TableHead className="hidden sm:table-cell">
                                                Created
                                            </TableHead>
                                            <TableHead className="hidden md:table-cell">
                                                Last Used
                                            </TableHead>
                                            <TableHead className="text-right">
                                                Actions
                                            </TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {keys.map((key) => (
                                            <TableRow
                                                key={key.keyId}
                                                className={
                                                    key.status === "revoked"
                                                        ? "opacity-50"
                                                        : ""
                                                }
                                            >
                                                <TableCell className="font-medium">
                                                    <div className="flex items-center gap-2">
                                                        <span>
                                                            {key.name}
                                                        </span>
                                                        {key.mode && (
                                                            <Badge
                                                                variant="outline"
                                                                className={`text-[10px] px-1.5 py-0 ${
                                                                    key.mode ===
                                                                    "test"
                                                                        ? "border-pending/30 text-pending"
                                                                        : "border-correct/30 text-correct"
                                                                }`}
                                                            >
                                                                {key.mode}
                                                            </Badge>
                                                        )}
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <code className="rounded bg-editorial-bg px-2 py-1 text-xs font-mono text-ink-2">
                                                        {key.mode === "test"
                                                            ? "capk_test_"
                                                            : "capk_live_"}
                                                        ...{key.lastFour}
                                                    </code>
                                                </TableCell>
                                                <TableCell>
                                                    <Badge
                                                        variant={
                                                            key.status ===
                                                            "active"
                                                                ? "default"
                                                                : "secondary"
                                                        }
                                                        className={
                                                            key.status ===
                                                            "active"
                                                                ? "bg-correct/10 text-correct border-correct/30"
                                                                : "bg-editorial-border text-ink-3"
                                                        }
                                                    >
                                                        {key.status}
                                                    </Badge>
                                                </TableCell>
                                                <TableCell className="hidden sm:table-cell text-ink-2 text-sm">
                                                    {formatDate(key.createdAt)}
                                                </TableCell>
                                                <TableCell className="hidden md:table-cell text-ink-2 text-sm">
                                                    {formatRelativeDate(
                                                        key.lastUsedAt
                                                    )}
                                                </TableCell>
                                                <TableCell className="text-right">
                                                    {key.status ===
                                                    "active" ? (
                                                        <div className="flex items-center justify-end gap-1">
                                                            <Tooltip>
                                                                <TooltipTrigger
                                                                    asChild
                                                                >
                                                                    <Button
                                                                        variant="ghost"
                                                                        size="icon"
                                                                        className="h-8 w-8"
                                                                        onClick={async () => {
                                                                            await navigator.clipboard.writeText(
                                                                                key.keyId
                                                                            );
                                                                        }}
                                                                    >
                                                                        <Copy className="h-3.5 w-3.5" />
                                                                    </Button>
                                                                </TooltipTrigger>
                                                                <TooltipContent>
                                                                    Copy Key ID
                                                                </TooltipContent>
                                                            </Tooltip>
                                                            <Tooltip>
                                                                <TooltipTrigger
                                                                    asChild
                                                                >
                                                                    <Button
                                                                        variant="ghost"
                                                                        size="icon"
                                                                        className="h-8 w-8"
                                                                        onClick={() => {
                                                                            setTargetKey(
                                                                                key
                                                                            );
                                                                            setRotateOpen(
                                                                                true
                                                                            );
                                                                        }}
                                                                    >
                                                                        <RotateCcw className="h-3.5 w-3.5" />
                                                                    </Button>
                                                                </TooltipTrigger>
                                                                <TooltipContent>
                                                                    Rotate Key
                                                                </TooltipContent>
                                                            </Tooltip>
                                                            <Tooltip>
                                                                <TooltipTrigger
                                                                    asChild
                                                                >
                                                                    <Button
                                                                        variant="ghost"
                                                                        size="icon"
                                                                        className="h-8 w-8 text-incorrect hover:text-incorrect/80 hover:bg-incorrect/10"
                                                                        onClick={() => {
                                                                            setTargetKey(
                                                                                key
                                                                            );
                                                                            setRevokeOpen(
                                                                                true
                                                                            );
                                                                        }}
                                                                    >
                                                                        <Trash2 className="h-3.5 w-3.5" />
                                                                    </Button>
                                                                </TooltipTrigger>
                                                                <TooltipContent>
                                                                    Revoke Key
                                                                </TooltipContent>
                                                            </Tooltip>
                                                        </div>
                                                    ) : (
                                                        <span className="text-xs text-ink-3">
                                                            Revoked
                                                        </span>
                                                    )}
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            )}
                        </CardContent>
                    </Card>
                </div>

                {/* ---------- Create Key Dialog ---------- */}
                <Dialog open={createOpen} onOpenChange={setCreateOpen}>
                    <DialogContent className="sm:max-w-md">
                        <DialogHeader>
                            <DialogTitle>Create New API Key</DialogTitle>
                            <DialogDescription>
                                Give your key a descriptive name so you can
                                identify it later.
                            </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 py-2">
                            <div className="space-y-2">
                                <Label htmlFor="key-name">Key Name</Label>
                                <Input
                                    id="key-name"
                                    placeholder="e.g., Production Backend"
                                    value={newKeyName}
                                    onChange={(e) =>
                                        setNewKeyName(e.target.value)
                                    }
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") handleCreate();
                                    }}
                                    autoFocus
                                />
                            </div>
                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="key-mode">
                                        Mode
                                    </Label>
                                    <p className="text-xs text-ink-2">
                                        {newKeyMode === "live"
                                            ? "Live keys access production data"
                                            : "Test keys return sandbox data"}
                                    </p>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span
                                        className={`text-xs font-medium ${
                                            newKeyMode === "test"
                                                ? "text-pending"
                                                : "text-ink-3"
                                        }`}
                                    >
                                        Test
                                    </span>
                                    <Switch
                                        id="key-mode"
                                        checked={newKeyMode === "live"}
                                        onChange={(e) =>
                                            setNewKeyMode(
                                                (
                                                    e.target as HTMLInputElement
                                                ).checked
                                                    ? "live"
                                                    : "test"
                                            )
                                        }
                                    />
                                    <span
                                        className={`text-xs font-medium ${
                                            newKeyMode === "live"
                                                ? "text-correct"
                                                : "text-ink-3"
                                        }`}
                                    >
                                        Live
                                    </span>
                                </div>
                            </div>
                        </div>
                        <DialogFooter>
                            <Button
                                variant="outline"
                                onClick={() => setCreateOpen(false)}
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={handleCreate}
                                disabled={
                                    !newKeyName.trim() || creating
                                }
                                className="gap-2"
                            >
                                {creating && (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                )}
                                Create Key
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                {/* ---------- Key Reveal Dialog ---------- */}
                <Dialog
                    open={revealDialogOpen}
                    onOpenChange={(open) => {
                        if (!open) {
                            setRevealDialogOpen(false);
                            setRevealKey(null);
                        }
                    }}
                >
                    <DialogContent className="sm:max-w-lg">
                        <DialogHeader>
                            <DialogTitle>Your New API Key</DialogTitle>
                            <DialogDescription>
                                Store this key securely. You will not be able to
                                see it again.
                            </DialogDescription>
                        </DialogHeader>
                        {revealKey && (
                            <KeyRevealPanel
                                plaintextKey={revealKey}
                                onDone={() => {
                                    setRevealDialogOpen(false);
                                    setRevealKey(null);
                                }}
                            />
                        )}
                    </DialogContent>
                </Dialog>

                {/* ---------- Revoke Confirmation Dialog ---------- */}
                <Dialog open={revokeOpen} onOpenChange={setRevokeOpen}>
                    <DialogContent className="sm:max-w-md">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <AlertTriangle className="h-5 w-5 text-incorrect" />
                                Revoke API Key
                            </DialogTitle>
                            <DialogDescription>
                                This will immediately disable{" "}
                                <strong className="text-ink">
                                    {targetKey?.name}
                                </strong>
                                . Any requests using this key will return 401
                                Unauthorized.
                            </DialogDescription>
                        </DialogHeader>
                        <DialogFooter>
                            <Button
                                variant="outline"
                                onClick={() => {
                                    setRevokeOpen(false);
                                    setTargetKey(null);
                                }}
                            >
                                Cancel
                            </Button>
                            <Button
                                variant="destructive"
                                onClick={handleRevoke}
                                disabled={revoking}
                                className="gap-2"
                            >
                                {revoking && (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                )}
                                Revoke Key
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                {/* ---------- Rotate Confirmation Dialog ---------- */}
                <Dialog open={rotateOpen} onOpenChange={setRotateOpen}>
                    <DialogContent className="sm:max-w-md">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <RotateCcw className="h-5 w-5 text-pending" />
                                Rotate API Key
                            </DialogTitle>
                            <DialogDescription>
                                This will revoke{" "}
                                <strong className="text-ink">
                                    {targetKey?.name}
                                </strong>{" "}
                                and create a new key with the same name. The old
                                key will stop working immediately.
                            </DialogDescription>
                        </DialogHeader>
                        <DialogFooter>
                            <Button
                                variant="outline"
                                onClick={() => {
                                    setRotateOpen(false);
                                    setTargetKey(null);
                                }}
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={handleRotate}
                                disabled={rotating}
                                className="gap-2"
                            >
                                {rotating && (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                )}
                                Rotate Key
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </main>
        </TooltipProvider>
    );
}
