"use client";

import React, { useState, useEffect } from "react";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from "recharts";
import { TrendingUp, Zap, AlertTriangle } from "lucide-react";

interface DailyRequest {
    date: string;
    count_2xx: number;
    count_4xx: number;
    count_5xx: number;
}

interface TopEndpoint {
    endpoint_path: string;
    count: number;
    pct: number;
}

interface RateLimitStatus {
    minute_current: number;
    minute_limit: number;
    day_current: number;
    day_limit: number;
}

interface UsageData {
    currentTier: string;
    tierName: string;
    monthlyQuota: number;
    renewalDate: string | null;
    dailyRequests: DailyRequest[];
    topEndpoints: TopEndpoint[];
    rateLimitStatus: RateLimitStatus;
    emptyState: boolean;
}

function formatNumber(n: number): string {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
    if (n >= 1000) return (n / 1000).toFixed(1) + "K";
    return n.toString();
}

function getTierColor(tier: string): string {
    const colors: Record<string, string> = {
        free: "bg-gray-100 text-gray-800",
        pro: "bg-blue-100 text-blue-800",
        agent: "bg-purple-100 text-purple-800",
        api_starter: "bg-emerald-100 text-emerald-800",
        api_growth: "bg-amber-100 text-amber-800",
        enterprise: "bg-red-100 text-red-800",
    };
    return colors[tier] || colors.free;
}

function getUpgradeUrl(): string {
    return "/pricing";
}

export function UsageDashboard() {
    const [data, setData] = useState<UsageData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch("/api/dashboard/usage")
            .then((res) => res.json())
            .then((data: UsageData) => {
                setData(data);
                setLoading(false);
            })
            .catch((err) => {
                console.error("Failed to fetch usage data:", err);
                setLoading(false);
            });
    }, []);

    if (loading) {
        return (
            <div className="space-y-6">
                <div className="h-32 bg-gray-200 animate-pulse rounded"></div>
                <div className="h-64 bg-gray-200 animate-pulse rounded"></div>
            </div>
        );
    }

    if (!data) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Usage Data Unavailable</CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-gray-600">
                        Could not load usage metrics. Please try again later.
                    </p>
                </CardContent>
            </Card>
        );
    }

    const totalRequests = data.dailyRequests.reduce(
        (sum, day) => sum + day.count_2xx + day.count_4xx + day.count_5xx,
        0
    );
    const successRate =
        totalRequests > 0
            ? (
                  (data.dailyRequests.reduce(
                      (sum, day) => sum + day.count_2xx,
                      0
                  ) /
                      totalRequests) *
                  100
              ).toFixed(1)
            : "100";

    const rateLimitHitFrequency = data.dailyRequests.filter(
        (day) => day.count_4xx > 20 || day.count_5xx > 5
    ).length;

    const shouldShowUpgradeBanner = rateLimitHitFrequency > 0;

    // Transform daily requests for chart (label each date)
    const chartData = data.dailyRequests.map((day) => ({
        ...day,
        label: new Date(day.date).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
        }),
    }));

    return (
        <div className="space-y-6">
            {/* Tier Card */}
            <Card>
                <CardHeader>
                    <div className="flex justify-between items-start">
                        <div>
                            <CardTitle>Current Tier</CardTitle>
                            <CardDescription>
                                Your subscription and quota
                            </CardDescription>
                        </div>
                        <Badge className={getTierColor(data.currentTier)}>
                            {data.tierName}
                        </Badge>
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-3 gap-4">
                        <div>
                            <p className="text-sm font-medium text-gray-600">
                                Monthly Quota
                            </p>
                            <p className="text-2xl font-bold">
                                {formatNumber(data.monthlyQuota)}
                            </p>
                            <p className="text-xs text-gray-500">
                                {totalRequests > 0
                                    ? `${formatNumber(totalRequests)} used`
                                    : "No requests yet"}
                            </p>
                        </div>
                        <div>
                            <p className="text-sm font-medium text-gray-600">
                                Success Rate
                            </p>
                            <p className="text-2xl font-bold">{successRate}%</p>
                            <p className="text-xs text-gray-500">
                                2xx responses
                            </p>
                        </div>
                        <div>
                            <p className="text-sm font-medium text-gray-600">
                                Resets On
                            </p>
                            <p className="text-2xl font-bold">
                                {data.renewalDate
                                    ? new Date(
                          data.renewalDate
                      ).toLocaleDateString()
                                    : "Next month"}
                            </p>
                            <p className="text-xs text-gray-500">
                                Quota cycle
                            </p>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Empty State */}
            {data.emptyState && (
                <Card className="border-blue-200 bg-blue-50">
                    <CardHeader>
                        <CardTitle className="text-blue-900 flex items-center gap-2">
                            <Zap className="w-5 h-5" />
                            No API requests yet
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-blue-800 mb-3">
                            Get started by creating an API key and making your
                            first request. Here's a quickstart snippet:
                        </p>
                        <pre className="bg-white p-3 rounded border border-blue-200 text-xs overflow-x-auto">
                            {`curl -H "Authorization: Bearer YOUR_API_KEY" \\
  https://api.pundit-ledger.com/v1/pundits`}
                        </pre>
                    </CardContent>
                </Card>
            )}

            {/* Upgrade Banner */}
            {shouldShowUpgradeBanner && (
                <Card className="border-amber-200 bg-amber-50">
                    <CardHeader>
                        <CardTitle className="text-amber-900 flex items-center gap-2">
                            <AlertTriangle className="w-5 h-5" />
                            Rate limits approaching
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-amber-800 mb-3">
                            You've hit rate limits {rateLimitHitFrequency} times
                            this month. Consider upgrading for higher quotas.
                        </p>
                        <Button asChild>
                            <a href={getUpgradeUrl()}>View Upgrade Options</a>
                        </Button>
                    </CardContent>
                </Card>
            )}

            {/* Daily Requests Chart */}
            {!data.emptyState && (
                <Card>
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="flex items-center gap-2">
                                    <TrendingUp className="w-5 h-5" />
                                    Request History
                                </CardTitle>
                                <CardDescription>
                                    Last 30 days (stacked by response status)
                                </CardDescription>
                            </div>
                            {totalRequests === 0 && (
                                <span className="text-xs text-gray-500">
                                    No data
                                </span>
                            )}
                        </div>
                    </CardHeader>
                    <CardContent>
                        {totalRequests > 0 ? (
                            <ResponsiveContainer width="100%" height={300}>
                                <BarChart data={chartData}>
                                    <CartesianGrid
                                        strokeDasharray="3 3"
                                        stroke="#f0f0f0"
                                    />
                                    <XAxis
                                        dataKey="label"
                                        tick={{ fontSize: 12 }}
                                        interval={
                                            chartData.length > 14 ? 2 : 0
                                        }
                                    />
                                    <YAxis tick={{ fontSize: 12 }} />
                                    <Tooltip
                                        formatter={(value) =>
                                            formatNumber(
                                                value as number
                                            )
                                        }
                                        labelFormatter={(label) =>
                                            `${label}`
                                        }
                                    />
                                    <Legend />
                                    <Bar
                                        dataKey="count_2xx"
                                        name="2xx Success"
                                        fill="#10b981"
                                        stackId="a"
                                    />
                                    <Bar
                                        dataKey="count_4xx"
                                        name="4xx Client Error"
                                        fill="#f59e0b"
                                        stackId="a"
                                    />
                                    <Bar
                                        dataKey="count_5xx"
                                        name="5xx Server Error"
                                        fill="#ef4444"
                                        stackId="a"
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="h-300 flex items-center justify-center text-gray-500">
                                <p>No request data available</p>
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Rate Limit Status */}
            <Card>
                <CardHeader>
                    <CardTitle>Current Rate Limit Status</CardTitle>
                    <CardDescription>
                        Real-time quota consumption
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    <div>
                        <div className="flex justify-between mb-2">
                            <span className="text-sm font-medium">
                                Requests per minute
                            </span>
                            <span className="text-sm text-gray-600">
                                {data.rateLimitStatus.minute_current} /{" "}
                                {formatNumber(
                                    data.rateLimitStatus.minute_limit
                                )}
                            </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                            <div
                                className={`h-2 rounded-full ${
                                    (data.rateLimitStatus.minute_current /
                                        data.rateLimitStatus.minute_limit) *
                                        100 >
                                    80
                                        ? "bg-red-500"
                                        : (data.rateLimitStatus
                            .minute_current /
                                        data.rateLimitStatus
                            .minute_limit) *
                                        100 >
                                    50
                                        ? "bg-amber-500"
                                        : "bg-green-500"
                                }`}
                                style={{
                                    width: `${Math.min(
                                        (data.rateLimitStatus
                            .minute_current /
                                            data.rateLimitStatus
                            .minute_limit) *
                                            100,
                                        100
                                    )}%`,
                                }}
                            ></div>
                        </div>
                    </div>

                    <div>
                        <div className="flex justify-between mb-2">
                            <span className="text-sm font-medium">
                                Requests per day
                            </span>
                            <span className="text-sm text-gray-600">
                                {data.rateLimitStatus.day_current} /{" "}
                                {formatNumber(
                                    data.rateLimitStatus.day_limit
                                )}
                            </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                            <div
                                className={`h-2 rounded-full ${
                                    (data.rateLimitStatus.day_current /
                                        data.rateLimitStatus.day_limit) *
                                        100 >
                                    80
                                        ? "bg-red-500"
                                        : (data.rateLimitStatus
                            .day_current /
                                        data.rateLimitStatus
                            .day_limit) *
                                        100 >
                                    50
                                        ? "bg-amber-500"
                                        : "bg-green-500"
                                }`}
                                style={{
                                    width: `${Math.min(
                                        (data.rateLimitStatus
                            .day_current /
                                            data.rateLimitStatus
                            .day_limit) *
                                            100,
                                        100
                                    )}%`,
                                }}
                            ></div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Top Endpoints */}
            {!data.emptyState && data.topEndpoints.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Top Endpoints</CardTitle>
                        <CardDescription>
                            Most-called endpoints in the last 30 days
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Endpoint</TableHead>
                                    <TableHead className="text-right">
                                        Requests
                                    </TableHead>
                                    <TableHead className="text-right">
                                        %
                                    </TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {data.topEndpoints.map((endpoint, idx) => (
                                    <TableRow key={idx}>
                                        <TableCell className="font-mono text-sm">
                                            {endpoint.endpoint_path}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            {formatNumber(endpoint.count)}
                                        </TableCell>
                                        <TableCell className="text-right text-gray-600">
                                            {endpoint.pct}%
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
