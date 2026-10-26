import { flushPromises } from "@vue/test-utils";
import { describe, expect, test, vi } from "vitest";
import { effectScope, ref } from "vue";
import { useRecipePantry } from "./use-recipe-pantry";

const pantryCheck = vi.fn();
vi.mock("~/composables/api", () => ({
  useUserApi: () => ({ householdCooking: { pantryCheck } }),
}));

const item = (id: string) => ({ id, name: id, groupId: "g", householdId: "h" });

function run(recipeId: () => string | undefined, enabled: () => boolean) {
  return effectScope().run(() => useRecipePantry(recipeId, enabled))!;
}

describe("useRecipePantry", () => {
  test("maps each ingredient to its pantry items", async () => {
    pantryCheck.mockResolvedValue({
      data: {
        items: [item("p1"), item("p2")],
        suggestedLeftoverPortions: 0,
        ingredients: [
          { referenceId: "ing-a", pantryItemIds: ["p2", "p1"] },
          { referenceId: "ing-b", pantryItemIds: [] },
        ],
      },
    });

    const { pantry } = run(() => "r-1", () => true);
    await flushPromises();

    expect(pantry.value).toEqual({ "ing-a": [item("p2"), item("p1")], "ing-b": [] });
  });

  test("stays unknown for visitors and when the check fails", async () => {
    pantryCheck.mockReset();
    const visitor = run(() => "r-1", () => false);
    await flushPromises();
    expect(pantryCheck).not.toHaveBeenCalled();
    expect(visitor.pantry.value).toBeNull();

    pantryCheck.mockRejectedValue(new Error("offline"));
    const offline = run(() => "r-1", () => true);
    await flushPromises();
    expect(offline.pantry.value).toBeNull();
  });

  test("a newer recipe's answer is not overwritten by an older one", async () => {
    let resolveFirst: (value: unknown) => void = () => {};
    pantryCheck.mockReset();
    pantryCheck
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce({ data: { items: [], suggestedLeftoverPortions: 0, ingredients: [{ referenceId: "new", pantryItemIds: [] }] } });
    const id = ref("r-old");

    const { pantry } = run(() => id.value, () => true);
    id.value = "r-new";
    await flushPromises();
    resolveFirst({ data: { items: [], suggestedLeftoverPortions: 0, ingredients: [{ referenceId: "old", pantryItemIds: [] }] } });
    await flushPromises();

    expect(pantry.value).toEqual({ new: [] });
  });
});
