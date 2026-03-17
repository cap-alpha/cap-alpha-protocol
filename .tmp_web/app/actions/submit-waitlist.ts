'use server'

import { db } from "@/db";
import { waitlist } from "@/db/schema";
import { sql } from "drizzle-orm";
import { revalidatePath } from "next/cache";

export async function submitWaitlist(formData: FormData) {
    const email = formData.get("email");
    const persona = formData.get("persona");

    if (!email || typeof email !== "string" || !email.includes("@")) {
        return { error: "Please enter a valid email address." };
    }

    try {
        await db.insert(waitlist).values({
            email: email,
            persona: (persona as string) || "General",
        });

        revalidatePath("/");
        return { success: true };
    } catch (e: any) {
        // Handle unique constraint violations gracefully
        if (e.code === '23505' || e.message?.includes('unique')) {
            return { success: true, message: "You're already on the list!" };
        }
        return { error: "Failed to join waitlist. Please try again later." };
    }
}
