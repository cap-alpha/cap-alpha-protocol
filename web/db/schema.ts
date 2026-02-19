
import { pgTable, serial, text, timestamp, jsonb, uuid, boolean } from "drizzle-orm/pg-core";

export const users = pgTable("users", {
    id: serial("id").primaryKey(),
    clerkId: text("clerk_id").unique().notNull(),
    email: text("email").notNull(),
    isPro: boolean("is_pro").default(false),
    createdAt: timestamp("created_at").defaultNow(),
});

export const scenarios = pgTable("scenarios", {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: text("user_id").references(() => users.clerkId).notNull(), // Foreign Key to Clerk ID
    name: text("name").notNull(),
    description: text("description"),
    rosterState: jsonb("roster_state").notNull(), // The JSON blob of the roster
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
});
