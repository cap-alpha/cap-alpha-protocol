import { SignUp } from "@clerk/nextjs";

export default function Page() {
    return (
        <main className="flex min-h-[100dvh] items-center justify-center bg-black">
            <SignUp />
        </main>
    );
}
