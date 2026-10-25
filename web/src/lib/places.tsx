"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { fetchExposure } from "@/lib/api";
import type { PlaceName } from "@/lib/describe";

export type Place = { id: string; name: string };

type Places = {
  shelters: Place[];
  communities: Place[];
  names: Record<string, string>;
};

const PlacesContext = createContext<Places>({
  shelters: [],
  communities: [],
  names: {},
});

/** Loads the shelters and communities once for everything below it. */
export function PlacesProvider({ children }: { children: React.ReactNode }) {
  const [shelters, setShelters] = useState<Place[]>([]);
  const [communities, setCommunities] = useState<Place[]>([]);

  useEffect(() => {
    fetchExposure()
      .then((e) => {
        setShelters(e.shelters);
        setCommunities(e.communities);
      })
      .catch(() => {});
  }, []);

  const value = useMemo(
    () => ({
      shelters,
      communities,
      names: Object.fromEntries([...shelters, ...communities].map((p) => [p.id, p.name])),
    }),
    [shelters, communities],
  );
  return <PlacesContext.Provider value={value}>{children}</PlacesContext.Provider>;
}

export function usePlaces(): Places {
  return useContext(PlacesContext);
}

/** Shelter or community id -> display name; falls back to the id until places load. */
export function usePlaceName(): PlaceName {
  const { names } = usePlaces();
  return (id: string) => names[id] ?? id;
}
