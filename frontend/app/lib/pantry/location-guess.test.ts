import { describe, expect, test } from "vitest";
import { guessLocation } from "./location-guess";

describe("guessLocation", () => {
  test.each([
    ["Dairy", "fridge"],
    ["Meat & Seafood", "fridge"],
    ["Produits laitiers", "fridge"],
    ["Frozen", "freezer"],
    ["Surgelés", "freezer"],
    // Freezer words win over fridge words: "Frozen fish" goes to the freezer.
    ["Frozen fish", "freezer"],
    ["Produce", "cupboard"],
    ["", "cupboard"],
    [undefined, "cupboard"],
  ])("%s → %s", (label, location) => {
    expect(guessLocation(label)).toBe(location);
  });
});
