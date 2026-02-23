import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET() {
    try {
        const filePath = path.join(process.cwd(), 'data', 'historical_predictions.json');

        if (!fs.existsSync(filePath)) {
            return NextResponse.json({ error: `File not found at ${filePath}` }, { status: 404 });
        }

        const data = fs.readFileSync(filePath, 'utf8');
        const parsed = JSON.parse(data);

        // Add delta to each element
        const extended = parsed.map((p: any) => ({
            ...p,
            delta: p.actual - p.predicted
        }));

        // Sort ascending for false positives (lowest delta)
        const falsePositives = [...extended].sort((a, b) => a.delta - b.delta).slice(0, 50);

        // Sort descending for false negatives (highest delta)
        const falseNegatives = [...extended].sort((a, b) => b.delta - a.delta).slice(0, 50);

        return NextResponse.json({
            falsePositives,
            falseNegatives
        });
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 });
    }
}
