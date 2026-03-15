import { auth } from "@clerk/nextjs/server";
import { PersonaShowcase } from "@/components/persona-showcase";

export default async function LandingPage() {
    const { userId } = await auth();

    // The Persona Showcase itself handles routing the user, 
    // but if we wanted to auto-route an already authenticated user, we would do it here. 
    // Since we don't know their persona, we let them pick on the landing page even if signed in for now.

    return <PersonaShowcase />;
}
