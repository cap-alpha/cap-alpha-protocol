
import { pgTable, serial, text, timestamp, jsonb, uuid, boolean } from "drizzle-orm/pg-core";

export const users = pgTable("users", {
    id: serial("id").primaryKey(),
    clerkId: text("clerk_id").unique().notNull(),
    email: text("email").notNull(),
    isPro: boolean("is_pro").default(false),
    stripeCustomerId: text("stripe_customer_id"),
    stripeSubscriptionId: text("stripe_subscription_id"),
    stripeSubscriptionStatus: text("stripe_subscription_status"),
    stripePriceId: text("stripe_price_id"),
    stripeCurrentPeriodEnd: timestamp("stripe_current_period_end"),
    tosAgreedAt: timestamp("tos_agreed_at"),
    tosVersion: text("tos_version"),
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

export const proofOfAlpha = pgTable("proof_of_alpha", {
    id: serial("id").primaryKey(),
    date: text("date").notNull(),
    playerName: text("player_name").notNull(),
    team: text("team").notNull(),
    contractSize: text("contract_size").notNull(),
    prediction: text("prediction").notNull(),
    mediaSentiment: text("media_sentiment").notNull(),
    capAlphaInsight: text("cap_alpha_insight").notNull(),
    outcome: text("outcome").notNull(),
    outcomeDate: text("outcome_date"),
    roi: text("roi").notNull(),
    trend: text("trend").notNull().default("down"),
    imageUrl: text("image_url"),
    imagePosition: text("image_position"),
    createdAt: timestamp("created_at").defaultNow(),
});

export const proofOfAlphaTweets = pgTable("proof_of_alpha_tweets", {
    id: serial("id").primaryKey(),
    proofOfAlphaId: serial("proof_of_alpha_id").references(() => proofOfAlpha.id, { onDelete: 'cascade' }).notNull(),
    text: text("text").notNull(),
    author: text("author").notNull(),
    url: text("url").notNull(),
    source: text("source").notNull().default("twitter"),
    likes: text("likes"),
    reposts: text("reposts"),
});
