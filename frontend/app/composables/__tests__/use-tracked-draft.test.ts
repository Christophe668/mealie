import { describe, expect, test } from "vitest";
import { nextTick, ref } from "vue";
import { useTrackedDraft } from "~/composables/use-tracked-draft";

interface Person {
  name: string;
  notes: string | null;
  dislikes: string[];
}

const normalise = (value: Person) => ({
  name: value.name.trim(),
  notes: value.notes?.trim() || null,
  dislikes: value.dislikes.map(item => item.trim()).filter(Boolean),
});

function setup(start: Partial<Person> = {}) {
  const source = ref<Person>({ name: "Sam", notes: null, dislikes: [], ...start });
  const tracked = useTrackedDraft(() => source.value, normalise);
  /** The source changes, as after a reload or Claude's edit. */
  async function update(patch: Partial<Person>) {
    source.value = { ...source.value, ...patch };
    await nextTick();
  }
  /** The user types into the draft. */
  async function type(patch: Partial<Person>) {
    Object.assign(tracked.draft.value, patch);
    await nextTick();
  }
  return { source, update, type, ...tracked };
}

describe("useTrackedDraft", () => {
  test("untouched fields follow the source, touched fields keep what was typed", async () => {
    const t = setup();
    await t.type({ name: "Sammy" });
    await t.update({ name: "Samuel", notes: "hi" });

    expect(t.draft.value.name).toBe("Sammy");
    expect(t.draft.value.notes).toBe("hi");
    expect(t.changes.value).toEqual({ name: "Sammy" });
  });

  test("a whitespace-only edit is not touched and still follows the source (m1)", async () => {
    const t = setup();
    await t.type({ name: "Sam ", notes: "  " });
    expect(t.changes.value).toEqual({});

    await t.update({ name: "Samuel", notes: "hi" });

    expect(t.draft.value.name).toBe("Samuel");
    expect(t.draft.value.notes).toBe("hi");
    expect(t.changes.value).toEqual({});
  });

  test("undoing an edit after the source changed that field shows the current source (m2)", async () => {
    const t = setup();
    await t.type({ name: "X" });
    await t.update({ name: "Samuel" });
    expect(t.draft.value.name).toBe("X");
    expect(t.changes.value).toEqual({ name: "X" });

    await t.type({ name: "Sam" });

    expect(t.draft.value.name).toBe("Samuel");
    expect(t.changes.value).toEqual({});
  });

  test("undo after a change to another field keeps the adopted value and leaves no changes", async () => {
    const t = setup();
    await t.type({ name: "X" });
    await t.update({ dislikes: ["mushrooms"] });
    await t.type({ name: "Sam" });

    expect(t.draft.value).toEqual({ name: "Sam", notes: null, dislikes: ["mushrooms"] });
    expect(t.changes.value).toEqual({});
  });

  test("typing exactly what the source now holds leaves nothing to send, and the field follows again", async () => {
    const t = setup();
    await t.type({ name: "X" });
    await t.update({ name: "Samuel" });
    await t.type({ name: "Samuel" });
    expect(t.changes.value).toEqual({});

    await t.update({ name: "Sammy" });

    expect(t.draft.value.name).toBe("Sammy");
  });

  test("a touched list wins over the source on that field", async () => {
    const t = setup({ dislikes: ["olives"] });
    await t.type({ dislikes: ["olives", "fennel"] });
    await t.update({ dislikes: ["olives", "mushrooms"] });

    expect(t.draft.value.dislikes).toEqual(["olives", "fennel"]);
    expect(t.changes.value).toEqual({ dislikes: ["olives", "fennel"] });
  });

  test("commit takes the saved value and keeps text typed while the save ran", async () => {
    const t = setup();
    await t.type({ name: "Sammy " });
    const sent = { ...t.changes.value };
    expect(sent).toEqual({ name: "Sammy" });

    // Typed during the save, then the source shows the saved record.
    await t.type({ name: "Sammy2" });
    t.source.value = { ...t.source.value, name: "Sammy" };
    t.commit(sent);
    await nextTick();

    expect(t.draft.value.name).toBe("Sammy2");
    expect(t.changes.value).toEqual({ name: "Sammy2" });

    // Undo back to the saved value: nothing left to send.
    await t.type({ name: "Sammy" });
    expect(t.changes.value).toEqual({});
  });

  test("commit replaces the draft with the record as the server stored it", async () => {
    const t = setup();
    await t.type({ dislikes: ["Fennel", "fennel"] });
    const sent = { ...t.changes.value };

    t.source.value = { ...t.source.value, dislikes: ["Fennel"] };
    t.commit(sent);
    await nextTick();

    expect(t.draft.value.dislikes).toEqual(["Fennel"]);
    expect(t.changes.value).toEqual({});
  });
});
