
import { Webhook } from 'svix'
import { headers } from 'next/headers'
import { WebhookEvent } from '@clerk/nextjs/server'
import { db } from '@/db'
import { users } from '@/db/schema'
import { eq } from 'drizzle-orm'

export async function POST(req: Request) {
    // You can find this in the Clerk Dashboard -> Webhooks -> choose the webhook
    const WEBHOOK_SECRET = process.env.CLERK_WEBHOOK_SECRET

    if (!WEBHOOK_SECRET) {
        console.error('Missing CLERK_WEBHOOK_SECRET');
        // In dev, we might not have webhooks setup, so don't crash, just return 400
        return new Response('Please add CLERK_WEBHOOK_SECRET from Clerk Dashboard to .env or .env.local', {
            status: 500
        })
    }

    // Get the headers
    const headerPayload = headers();
    const svix_id = headerPayload.get("svix-id");
    const svix_timestamp = headerPayload.get("svix-timestamp");
    const svix_signature = headerPayload.get("svix-signature");

    // If there are no headers, error out
    if (!svix_id || !svix_timestamp || !svix_signature) {
        return new Response('Error occured -- no svix headers', {
            status: 400
        })
    }

    // Get the body
    const payload = await req.json()
    const body = JSON.stringify(payload);

    // Create a new Svix instance with your secret.
    const wh = new Webhook(WEBHOOK_SECRET);

    let evt: WebhookEvent

    // Verify the payload with the headers
    try {
        evt = wh.verify(body, {
            "svix-id": svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": svix_signature,
        }) as WebhookEvent
    } catch (err) {
        console.error('Error verifying webhook:', err);
        return new Response('Error occured', {
            status: 400
        })
    }

    // Handle the event
    const eventType = evt.type;

    if (eventType === 'user.created') {
        const { id, email_addresses } = evt.data;
        // @ts-ignore
        const email = email_addresses[0]?.email_address;

        if (email) {
            try {
                await db.insert(users).values({
                    clerkId: id,
                    email: email,
                }).onConflictDoNothing();
                console.log(`User created: ${email}`);
            } catch (e) {
                console.error('Error inserting user:', e);
            }
        }
    } else if (eventType === 'user.updated') {
        const { id, email_addresses } = evt.data;
        // @ts-ignore
        const email = email_addresses[0]?.email_address;

        if (email) {
            try {
                await db.update(users).set({ email }).where(eq(users.clerkId, id));
                console.log(`User updated: ${email}`);
            } catch (e) {
                console.error('Error updating user:', e);
            }
        }
    } else if (eventType === 'user.deleted') {
        const { id } = evt.data;
        if (id) {
            try {
                await db.delete(users).where(eq(users.clerkId, id));
                console.log(`User deleted: ${id}`);
            } catch (e) {
                console.error('Error deleting user:', e);
            }
        }
    }

    return new Response('', { status: 200 })
}
