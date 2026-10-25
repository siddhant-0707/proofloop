"use client";

import { useState } from "react";

import HazardMap from "@/components/HazardMap";
import RoundsPanel from "@/components/RoundsPanel";
import { DEFAULT_SCENARIO, type Scenario } from "@/lib/api";

/** Holds the base Scenario the user edits, shared by the map and the stress-test panel. */
export default function Dashboard() {
  const [scenario, setScenario] = useState<Scenario>(DEFAULT_SCENARIO);
  return (
    <div className="grid flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="h-[75vh] lg:sticky lg:top-4 lg:h-[calc(100vh-7rem)] lg:self-start">
        <HazardMap scenario={scenario} />
      </div>
      <RoundsPanel scenario={scenario} onScenarioChange={setScenario} />
    </div>
  );
}
