import type { PantryLocation } from "~/lib/api/types/household";

// Copied from `_FREEZER_LABEL_WORDS` / `_FRIDGE_LABEL_WORDS` in
// mealie/services/claude_context/pantry_service.py; keep the two in step.
const FREEZER_LABEL_WORDS = ["frozen", "surgel"];
const FRIDGE_LABEL_WORDS = [
  "dairy",
  "fresh",
  "meat",
  "seafood",
  "fish",
  "poultry",
  "frais",
  "laitier",
  "viande",
  "charcuterie",
  "poisson",
  "produits de la mer",
  "volaille",
];

/**
 * Where put away would file a shopping item, from its label: the same rule as `PantryService._location_for`
 * (case-insensitive substring, freezer words first, then fridge words, else the cupboard). Only preselects a
 * place chip; the server receives the place the user chose.
 */
export function guessLocation(labelName: string | undefined): PantryLocation {
  const label = (labelName ?? "").toLowerCase();
  if (FREEZER_LABEL_WORDS.some(word => label.includes(word))) {
    return "freezer";
  }
  if (FRIDGE_LABEL_WORDS.some(word => label.includes(word))) {
    return "fridge";
  }
  return "cupboard";
}
