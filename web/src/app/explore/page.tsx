import type { Metadata } from "next";
import { Explorer } from "@/components/globe/Explorer";

export const metadata: Metadata = {
  title: "Earth Explorer",
  description: "Interactive 3D globe with AETHENTRA model layers, ERA5 anomalies and NASA satellite imagery over Antarctica.",
};

export default function ExplorePage() {
  return (
    <main id="main">
      <h1 className="sr-only">AETHENTRA Earth Explorer</h1>
      <Explorer />
    </main>
  );
}
