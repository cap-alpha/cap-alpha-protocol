
"use client";

import React, { createContext, useContext, useState, ReactNode } from "react";

export type Persona = "FAN" | "BETTOR" | "AGENT";

interface PersonaContextType {
    persona: Persona;
    setPersona: (p: Persona) => void;
}

const PersonaContext = createContext<PersonaContextType | undefined>(undefined);

export function PersonaProvider({ children }: { children: ReactNode }) {
    const [persona, setPersona] = useState<Persona>("FAN");

    return (
        <PersonaContext.Provider value={{ persona, setPersona }}>
            {children}
        </PersonaContext.Provider>
    );
}

export function usePersona() {
    const context = useContext(PersonaContext);
    if (context === undefined) {
        throw new Error("usePersona must be used within a PersonaProvider");
    }
    return context;
}
