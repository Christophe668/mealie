import { describe, expect, test } from "vitest";
import { stepAction } from "./step-action";

const key = (text: string | null | undefined) => stepAction(text)?.key ?? null;

describe("stepAction", () => {
  test("reads the main action of common English steps", () => {
    expect(key("Preheat the oven to 200°C.")).toBe("preheat");
    expect(key("Finely chop the onion and garlic.")).toBe("cut");
    expect(key("Peel the potatoes.")).toBe("peel");
    expect(key("Whisk the eggs with the sugar until pale.")).toBe("whisk");
    expect(key("In a large bowl, mix the flour and salt.")).toBe("mix");
    expect(key("Knead for 10 minutes.")).toBe("knead");
    expect(key("Blend until smooth.")).toBe("blend");
    expect(key("Bring a large pot of salted water to the boil.")).toBe("boil");
    expect(key("Simmer for 20 minutes.")).toBe("simmer");
    expect(key("Sauté the onions until soft.")).toBe("saute");
    expect(key("Sear the steak on both sides.")).toBe("fry");
    expect(key("Roast for 45 minutes.")).toBe("roast");
    expect(key("Bake for 25 minutes until golden.")).toBe("bake");
    expect(key("Heat the oil in a pan.")).toBe("heat");
    expect(key("Cook the pasta until al dente.")).toBe("cook");
    expect(key("Chill for at least 2 hours.")).toBe("chill");
    expect(key("Let the dough rest for 30 minutes.")).toBe("rest");
    expect(key("Season with salt and pepper.")).toBe("season");
    expect(key("Drain and set aside.")).toBe("drain");
    expect(key("Serve with crusty bread.")).toBe("serve");
  });

  test("reads French steps, infinitive or imperative", () => {
    expect(key("Préchauffer le four à 180 °C.")).toBe("preheat");
    expect(key("Émincez les oignons.")).toBe("cut");
    expect(key("Faire revenir les lardons.")).toBe("saute");
    expect(key("Faites cuire au four 30 minutes.")).toBe("bake");
    expect(key("Laisser reposer la pâte 1 h.")).toBe("rest");
    expect(key("Égoutter les pâtes.")).toBe("drain");
    expect(key("Porter l'eau à ébullition.")).toBe("boil");
  });

  test("the earliest action wins, a tie goes to the longer phrase", () => {
    expect(key("Preheat the oven, then chop the onions.")).toBe("preheat");
    expect(key("Take the chicken out of the fridge and heat the oven to 220 °C.")).toBe("preheat");
    expect(key("Rest the chicken under foil for 15 minutes.")).toBe("rest");
    expect(key("Cook in the oven for 20 minutes.")).toBe("bake");
    expect(key("Let cool, then slice.")).toBe("cool");
  });

  test("nouns and past participles are not actions", () => {
    expect(key("Add the rest of the butter.")).toBeNull();
    expect(key("Add the brown sugar and a stock cube.")).toBeNull();
    expect(key("Add the chopped onions.")).toBeNull();
    expect(key("Put everything on a plate.")).toBeNull();
    expect(key("This dish serves four.")).toBeNull();
    expect(key("Add the orange peel and the lemon zest.")).toBeNull();
    expect(key("Top with a slice of cheese.")).toBeNull();
    expect(key("Add the onions over medium heat.")).toBeNull();
  });

  test("English verbs count after punctuation, linking words and adverbs", () => {
    expect(key("Meanwhile, finely chop the parsley.")).toBe("cut");
    expect(key("Add the onions and fry until golden.")).toBe("fry");
    expect(key("**Stir** in the cream.")).toBe("mix");
  });

  test("no text, no action", () => {
    expect(key("")).toBeNull();
    expect(key(null)).toBeNull();
    expect(key("Add the tomatoes.")).toBeNull();
  });

  test("gives the icon with the action", () => {
    expect(stepAction("Bake for 20 minutes.")).toEqual({ key: "bake", icon: "oven" });
  });
});
