import { format } from "date-fns";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { useIngredientPantryActions } from "./use-ingredient-pantry-actions";
import type { PantryItemOut, ShoppingListSummary } from "~/lib/api/types/household";
import type { RecipeIngredient } from "~/lib/api/types/recipe";

const api = vi.hoisted(() => ({
  createOne: vi.fn(),
  updateOne: vi.fn(),
  deleteOne: vi.fn(),
  createItem: vi.fn(),
  addRecipes: vi.fn(),
}));
const toast = vi.hoisted(() => ({ info: vi.fn(), error: vi.fn(), unreported: vi.fn() }));
const push = vi.fn();

vi.mock("~/composables/api", () => ({
  useUserApi: () => ({
    householdPantry: { createOne: api.createOne, updateOne: api.updateOne, deleteOne: api.deleteOne },
    shopping: { items: { createOne: api.createItem }, lists: { addRecipes: api.addRecipes } },
  }),
}));
vi.mock("~/composables/use-toast", () => ({
  alert: { info: toast.info, error: toast.error },
  alertUnreportedError: toast.unreported,
}));
vi.mock("vue-i18n", async importOriginal => ({
  ...(await importOriginal<typeof import("vue-i18n")>()),
  useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => (params ? `${key} ${JSON.stringify(params)}` : key) }),
}));

const lemon: RecipeIngredient = {
  referenceId: "ing-lemon",
  quantity: 2,
  unit: { id: "u-piece", name: "piece" },
  food: { id: "f-lemon", name: "lemon" },
  note: "zested",
};
const row = (extra: Partial<PantryItemOut> = {}): PantryItemOut => ({
  id: "p1",
  name: "lemon",
  foodId: "f-lemon",
  location: "fridge",
  source: "manual",
  groupId: "g",
  householdId: "h",
  ...extra,
});
const list: ShoppingListSummary = {
  id: "l1",
  name: "Weekly shop",
  groupId: "g",
  userId: "u",
  householdId: "h",
  recipeReferences: [],
  labelSettings: [],
};

let pantry: Record<string, PantryItemOut[]>;
const setItems = vi.fn((referenceId: string, items: PantryItemOut[]) => {
  pantry[referenceId] = items;
});

function actions(scale = 1) {
  return useIngredientPantryActions({
    recipeId: () => "r1",
    scale: () => scale,
    setItems,
    items: referenceId => pantry[referenceId] ?? [],
    lists: () => [list],
  });
}

/** Runs the toast action (Undo or Open list) of the last info toast. */
async function clickToastAction() {
  const options = toast.info.mock.calls.at(-1)![2];
  await options.action.onClick();
}

beforeEach(() => {
  vi.resetAllMocks();
  setItems.mockImplementation((referenceId: string, items: PantryItemOut[]) => {
    pantry[referenceId] = items;
  });
  pantry = { "ing-lemon": [] };
  vi.stubGlobal("useRouter", () => ({ push }));
});

describe("useIngredientPantryActions", () => {
  test("iHaveIt creates a manual pantry item in the chosen place", async () => {
    api.createOne.mockResolvedValue({ data: row({ id: "new", location: "freezer" }) });
    const { iHaveIt } = actions();

    await iHaveIt(lemon, "freezer", "2026-11-02");

    expect(api.createOne).toHaveBeenCalledWith({
      name: "lemon",
      foodId: "f-lemon",
      location: "freezer",
      useBy: "2026-11-02",
      source: "manual",
    });
    expect(setItems).toHaveBeenCalledWith("ing-lemon", [row({ id: "new", location: "freezer" })]);
    expect(toast.info).toHaveBeenCalledOnce();
  });

  test("undo of iHaveIt deletes the created item", async () => {
    api.createOne.mockResolvedValue({ data: row({ id: "new" }) });
    api.deleteOne.mockResolvedValue({ data: row({ id: "new" }) });
    const { iHaveIt } = actions();
    await iHaveIt(lemon, "fridge");

    await clickToastAction();

    expect(api.deleteOne).toHaveBeenCalledWith("new");
    expect(pantry["ing-lemon"]).toEqual([]);
  });

  test("usedUp undo recreates the row", async () => {
    const held = row({ id: "p1", useBy: "2026-11-01", openedOn: "2026-10-28" });
    pantry["ing-lemon"] = [held, row({ id: "p2", location: "freezer" })];
    api.deleteOne.mockResolvedValue({ data: held });
    api.createOne.mockResolvedValue({ data: { ...held, id: "p3" } });
    const { usedUp } = actions();

    await usedUp(lemon, held);
    expect(api.deleteOne).toHaveBeenCalledWith("p1");
    expect(pantry["ing-lemon"]!.map(item => item.id)).toEqual(["p2"]);

    await clickToastAction();
    expect(api.createOne).toHaveBeenCalledWith(expect.objectContaining({
      name: "lemon",
      foodId: "f-lemon",
      location: "fridge",
      useBy: "2026-11-01",
      openedOn: "2026-10-28",
      source: "manual",
    }));
    expect(pantry["ing-lemon"]!.map(item => item.id)).toEqual(["p2", "p3"]);
  });

  test("usedUp undo merged into a row already shown replaces that row instead of adding it twice", async () => {
    const held = row({ id: "p1", location: "fridge" });
    const frozen = row({ id: "p2", location: "freezer" });
    pantry["ing-lemon"] = [held, frozen];
    api.deleteOne.mockResolvedValue({ data: held });
    // The server folds the recreated row into the freezer one (same food), returning its id.
    api.createOne.mockResolvedValue({ data: { ...frozen, useBy: "2026-11-05" } });
    const { usedUp } = actions();

    await usedUp(lemon, held);
    await clickToastAction();

    expect(pantry["ing-lemon"]!.map(item => item.id)).toEqual(["p2"]);
    expect(pantry["ing-lemon"]![0]!.useBy).toBe("2026-11-05");
  });

  test("iHaveIt merged into a row already shown replaces that row", async () => {
    pantry["ing-lemon"] = [row({ id: "p1" })];
    api.createOne.mockResolvedValue({ data: row({ id: "p1", useBy: "2026-11-02" }) });
    const { iHaveIt } = actions();

    await iHaveIt(lemon, "fridge", "2026-11-02");

    expect(pantry["ing-lemon"]!.map(item => item.id)).toEqual(["p1"]);
    expect(pantry["ing-lemon"]![0]!.useBy).toBe("2026-11-02");
  });

  test("undo of an iHaveIt that merged puts the row back as it was instead of deleting it", async () => {
    const held = row({ id: "p1", useBy: null });
    pantry["ing-lemon"] = [held];
    api.createOne.mockResolvedValue({ data: row({ id: "p1", useBy: "2026-11-02" }) });
    api.updateOne.mockResolvedValue({ data: held });
    const { iHaveIt } = actions();
    await iHaveIt(lemon, "fridge", "2026-11-02");

    await clickToastAction();

    expect(api.deleteOne).not.toHaveBeenCalled();
    expect(api.updateOne).toHaveBeenCalledWith("p1", expect.objectContaining({ useBy: null }));
    expect(pantry["ing-lemon"]).toEqual([held]);
  });

  test("openedToday undo restores the previous date", async () => {
    const today = format(new Date(), "yyyy-MM-dd");
    const held = row({ openedOn: "2026-10-20" });
    pantry["ing-lemon"] = [held];
    api.updateOne
      .mockResolvedValueOnce({ data: row({ openedOn: today }) })
      .mockResolvedValueOnce({ data: row({ openedOn: "2026-10-20" }) });
    const { openedToday } = actions();

    await openedToday(lemon, held);
    expect(api.updateOne).toHaveBeenLastCalledWith("p1", expect.objectContaining({ openedOn: today }));
    expect(pantry["ing-lemon"]![0]!.openedOn).toBe(today);

    await clickToastAction();
    expect(api.updateOne).toHaveBeenLastCalledWith("p1", expect.objectContaining({ openedOn: "2026-10-20" }));
    expect(pantry["ing-lemon"]![0]!.openedOn).toBe("2026-10-20");
  });

  test("addToList scales the quantity", async () => {
    api.createItem.mockResolvedValue({ data: {} });
    const { addToList } = actions(1.5);

    await addToList(lemon, "l1");

    expect(api.createItem).toHaveBeenCalledWith({
      shoppingListId: "l1",
      foodId: "f-lemon",
      unitId: "u-piece",
      quantity: 3,
      note: "zested",
    });
    expect(setItems).not.toHaveBeenCalled();
    expect(toast.info.mock.calls[0]![0]).toContain("Weekly shop");
    await clickToastAction();
    expect(push).toHaveBeenCalledWith("/shopping-lists/l1");
  });

  test("adds a quantity-less ingredient as 1", async () => {
    api.createItem.mockResolvedValue({ data: {} });
    const { addToList } = actions();

    await addToList({ referenceId: "ing-salt", quantity: 0, food: { id: "f-salt", name: "salt" } }, "l1");

    expect(api.createItem).toHaveBeenCalledWith(expect.objectContaining({ quantity: 1, note: "", unitId: undefined }));
  });

  test("at scale 2, a quantity-less ingredient is still added as 1, and a quantity of 2 as 4", async () => {
    api.createItem.mockResolvedValue({ data: {} });
    const { addToList } = actions(2);

    await addToList({ referenceId: "ing-salt", quantity: 0, food: { id: "f-salt", name: "salt" } }, "l1");
    await addToList(lemon, "l1");

    expect(api.createItem.mock.calls.map(([body]) => body.quantity)).toEqual([1, 4]);
  });

  test("addMissing sends one addRecipes call with the missing ingredients and the scale", async () => {
    api.addRecipes.mockResolvedValue({ data: {} });
    const salt: RecipeIngredient = { referenceId: "ing-salt", food: { id: "f-salt", name: "salt" } };
    const { addMissing } = actions(2);

    await addMissing([lemon, salt], "l1");

    expect(api.addRecipes).toHaveBeenCalledOnce();
    expect(api.addRecipes).toHaveBeenCalledWith("l1", [
      { recipeId: "r1", recipeIncrementQuantity: 2, recipeIngredients: [lemon, salt] },
    ]);
    expect(toast.info).toHaveBeenCalledOnce();
  });

  test("ignores a second tap while saving", async () => {
    let resolve: (value: unknown) => void = () => {};
    api.createOne.mockImplementation(() => new Promise((r) => { resolve = r; }));
    const { iHaveIt, busy } = actions();

    const first = iHaveIt(lemon, "fridge");
    expect(busy.value).toBe(true);
    await iHaveIt(lemon, "fridge");
    resolve({ data: row({ id: "new" }) });
    await first;

    expect(api.createOne).toHaveBeenCalledOnce();
    expect(busy.value).toBe(false);
  });

  test("a failed action reports the error and leaves the items", async () => {
    api.deleteOne.mockResolvedValue({ data: null, error: { response: {} } });
    pantry["ing-lemon"] = [row()];
    const { usedUp } = actions();

    expect(await usedUp(lemon, row())).toBe(false);

    expect(toast.unreported).toHaveBeenCalledOnce();
    expect(setItems).not.toHaveBeenCalled();
    expect(toast.info).not.toHaveBeenCalled();
  });

  test("undo failure shows an error", async () => {
    api.createOne.mockResolvedValue({ data: row({ id: "new" }) });
    api.deleteOne.mockResolvedValue({ data: null, error: { response: {} } });
    const { iHaveIt } = actions();
    await iHaveIt(lemon, "fridge");

    await clickToastAction();

    expect(toast.unreported).toHaveBeenCalledWith({ response: {} }, "recipe-ingredient-sheet.undo-failed");
    expect(pantry["ing-lemon"]!.map(item => item.id)).toEqual(["new"]);
  });

  test("edit saves the row and undo puts the old place and use-by back", async () => {
    const held = row({ location: "fridge", useBy: "2026-11-01" });
    pantry["ing-lemon"] = [held];
    api.updateOne
      .mockResolvedValueOnce({ data: row({ location: "freezer", useBy: null }) })
      .mockResolvedValueOnce({ data: held });
    const { edit } = actions();

    expect(await edit(lemon, held, { name: "lemon", location: "freezer", useBy: null })).toBe(true);
    expect(pantry["ing-lemon"]![0]!.location).toBe("freezer");

    await clickToastAction();
    expect(api.updateOne).toHaveBeenLastCalledWith("p1", expect.objectContaining({ location: "fridge", useBy: "2026-11-01" }));
    expect(pantry["ing-lemon"]![0]!.location).toBe("fridge");
  });
});
