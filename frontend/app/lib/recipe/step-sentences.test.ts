import { describe, expect, test } from "vitest";
import { stepMarkdown, stepSentences } from "./step-sentences";

describe("stepSentences", () => {
  test("one sentence per bullet; brackets stay with their sentence", () => {
    expect(stepSentences(
      "Vérifier que le saumon est opaque à cœur (sinon, prolonger de 3 min). Retirer le Varoma et le garder fermé pour conserver la chaleur. Sortir le panier de riz avec la spatule, égrainer et réserver. Vider le bol.",
    )).toEqual([
      "Vérifier que le saumon est opaque à cœur (sinon, prolonger de 3 min).",
      "Retirer le Varoma et le garder fermé pour conserver la chaleur.",
      "Sortir le panier de riz avec la spatule, égrainer et réserver.",
      "Vider le bol.",
    ]);
  });

  test("numbers, abbreviations and lowercase continuations don't split", () => {
    expect(stepSentences("Ajouter 1.5 kg de pommes de terre, env. 3 min à 180 °C.")).toBeNull();
    expect(stepSentences("Mettre 2 c. à s. d'huile. Chauffer 2 min.")).toEqual(["Mettre 2 c. à s. d'huile.", "Chauffer 2 min."]);
    expect(stepSentences("Bien mélanger ! Laisser reposer… Servir chaud?")).toEqual(["Bien mélanger !", "Laisser reposer…", "Servir chaud?"]);
    expect(stepSentences("Cuire 10 min (voir la note.) Ajouter le sel.")).toEqual(["Cuire 10 min (voir la note.)", "Ajouter le sel."]);
  });

  test("single sentences and steps laid out by their author stay as written", () => {
    expect(stepSentences("Vider le bol.")).toBeNull();
    expect(stepSentences("Première ligne.\nDeuxième ligne.")).toBeNull();
    expect(stepSentences("")).toBeNull();
    expect(stepSentences(null)).toBeNull();
  });

  test("stepMarkdown turns several sentences into a Markdown list", () => {
    expect(stepMarkdown("Rincer le riz. Égoutter.")).toBe("- Rincer le riz.\n- Égoutter.");
    expect(stepMarkdown("Vider le bol.")).toBe("Vider le bol.");
  });
});
