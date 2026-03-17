
"use client";

import { useState } from "react";
import { useUser, SignInButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Save, Loader2 } from "lucide-react";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface SaveScenarioButtonProps {
    rosterState: any; // The current state of the roster (post-cuts)
    // @ts-ignore
    defaultName?: string;
}

export function SaveScenarioButton({ rosterState, defaultName = "My Roster Scenario" }: SaveScenarioButtonProps) {
    // @ts-ignore
    const { isSignedIn, user } = useUser();
    const [isOpen, setIsOpen] = useState(false);
    const [name, setName] = useState(defaultName);
    const [isLoading, setIsLoading] = useState(false);

    const handleSave = async () => {
        setIsLoading(true);
        try {
            const res = await fetch("/api/scenarios", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: name,
                    description: `Saved by ${(user as any)?.fullName || "User"}`,
                    rosterState: rosterState,
                }),
            });

            if (!res.ok) throw new Error("Failed to save");

            setIsOpen(false);
            // Ideally show a toast here
            alert("Scenario Saved!");
        } catch (error) {
            console.error(error);
            alert("Error saving scenario");
        } finally {
            setIsLoading(false);
        }
    };

    if (!isSignedIn) {
        return (
            <SignInButton mode="modal">
                <Button variant="outline" className="gap-2">
                    <Save className="h-4 w-4" />
                    Sign in to Save
                </Button>
            </SignInButton>
        );
    }

    return (
        <Dialog open={isOpen} onOpenChange={setIsOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" className="gap-2">
                    <Save className="h-4 w-4" />
                    Save Scenario
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle>Save Roster Scenario</DialogTitle>
                    <DialogDescription>
                        Save your current cuts and cap space to your profile.
                    </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="name" className="text-right">
                            Name
                        </Label>
                        <Input
                            id="name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className="col-span-3"
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button onClick={handleSave} disabled={isLoading}>
                        {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Save changes
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
