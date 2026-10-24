import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import RecipeReadFeedback from "./RecipeReadFeedback.vue";
import type { RecipeFeedbackOut } from "~/lib/api/types/household";

const api = vi.hoisted(() => ({ list: vi.fn(), remove: vi.fn() }));

vi.mock("~/composables/api", () => ({
  useUserApi: () => ({ recipeFeedback: { list: api.list, remove: api.remove } }),
}));

const stubs = {
  "v-dialog": { props: ["modelValue"], template: "<div v-if=\"modelValue\" class=\"v-dialog-stub\"><slot /></div>" },
  "BaseDialog": {
    props: ["modelValue", "title"],
    emits: ["confirm", "update:modelValue"],
    template: "<div v-if=\"modelValue\" class=\"confirm-stub\"><p>{{ title }}</p><button @click=\"$emit('confirm'); $emit('update:modelValue', false)\">Confirm</button></div>",
  },
};

let nextId = 1;
function feedback(madeOn: string, fields: Partial<RecipeFeedbackOut> = {}): RecipeFeedbackOut {
  const id = `fb-${nextId++}`;
  return {
    id,
    groupId: "g",
    householdId: "h",
    recipeId: "r-1",
    verdict: "loved",
    madeOn,
    recipe: { id: "r-1", slug: "onion-soup", name: "Onion soup" },
    ...fields,
  };
}

function ok<T>(items: T[]) {
  return Promise.resolve({ data: { page: 1, per_page: -1, total: items.length, total_pages: 1, items }, error: null });
}

function render(props: Partial<{ recipeId: string; signedIn: boolean }> = {}) {
  return mount(RecipeReadFeedback, {
    props: { recipeId: "r-1", signedIn: true, ...props },
    global: { stubs, mocks: { $globals: { icons: {} } } },
    attachTo: document.body,
  });
}

const entries = (wrapper: ReturnType<typeof render>) => wrapper.findAll(".read-feedback__list > .read-feedback__entry");

beforeEach(() => {
  // Saturday 24 October 2026.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 24, 15, 30));
  api.list.mockImplementation(() => ok([]));
  api.remove.mockImplementation(() => Promise.resolve({ data: {}, error: null }));
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
  document.body.innerHTML = "";
});

describe("RecipeReadFeedback", () => {
  test("shows at most three entries, newest first", async () => {
    api.list.mockImplementation(() => ok([
      feedback("2026-09-01", { verdict: "ok" }),
      feedback("2026-10-22", { verdict: "loved" }),
      feedback("2026-06-01", { verdict: "ok" }),
      feedback("2026-10-10", { verdict: "never_again" }),
    ]));
    const wrapper = render();
    await flushPromises();

    expect(wrapper.find("h2").text()).toBe("How it went");
    expect(entries(wrapper).map(e => e.find(".read-feedback__verdict").text())).toEqual([
      "Loved it",
      "Not again",
      "It was fine",
    ]);
    expect(api.list).toHaveBeenCalledWith("r-1", 1, 3);
    wrapper.unmount();
  });

  test("each entry: the verdict, one line with when and for whom, effort as a chip, then the note", async () => {
    api.list.mockImplementation(() => ok([
      feedback("2026-10-10", { verdict: "loved", forWhom: "Sam", effort: 3, note: "Less salt next time." }),
      feedback("2026-10-01", { verdict: "ok" }),
    ]));
    const wrapper = render();
    await flushPromises();

    const [full, bare] = entries(wrapper);
    expect(full!.find(".read-feedback__when").text()).toBe("2 weeks ago, for Sam");
    expect(full!.find(".ds-chip").text()).toBe("A lot of work");
    expect(full!.find(".read-feedback__note").text()).toBe("Less salt next time.");
    expect(full!.text()).not.toMatch(/[·•]/);

    expect(bare!.find(".read-feedback__when").text()).toBe("3 weeks ago");
    expect(bare!.find(".ds-chip").exists()).toBe(false);
    expect(bare!.find(".read-feedback__note").exists()).toBe(false);
    wrapper.unmount();
  });

  test("a recent day reads in sentence case", async () => {
    api.list.mockImplementation(() => ok([feedback("2026-10-23", { forWhom: "Sam" })]));
    const wrapper = render();
    await flushPromises();

    expect(wrapper.find(".read-feedback__when").text()).toBe("Yesterday, for Sam");
    wrapper.unmount();
  });

  test("hidden when the recipe has no feedback", async () => {
    const wrapper = render();
    await flushPromises();

    expect(wrapper.find(".read-feedback").exists()).toBe(false);
    wrapper.unmount();
  });

  test("hidden, without a request, for someone not signed in", async () => {
    const wrapper = render({ signedIn: false });
    await flushPromises();

    expect(api.list).not.toHaveBeenCalled();
    expect(wrapper.find(".read-feedback").exists()).toBe(false);
    wrapper.unmount();
  });

  test("a failed load hides the block without a word", async () => {
    api.list.mockImplementation(() => Promise.resolve({ data: null, error: new Error("offline") }));
    const wrapper = render();
    await flushPromises();

    expect(wrapper.find(".read-feedback").exists()).toBe(false);
    expect(wrapper.text()).toBe("");
    wrapper.unmount();
  });

  test("See all lists everything; deleting an entry asks first, then refreshes the block", async () => {
    const all = [
      feedback("2026-10-22", { verdict: "loved" }),
      feedback("2026-10-10", { verdict: "never_again" }),
      feedback("2026-09-01", { verdict: "ok" }),
      feedback("2026-06-01", { verdict: "ok", note: "Too long" }),
    ];
    let current = [...all];
    api.list.mockImplementation((_id: string, _page: number, perPage: number) =>
      ok(perPage > 0 ? current.slice(0, perPage) : current),
    );
    api.remove.mockImplementation((id: string) => {
      current = current.filter(item => item.id !== id);
      return Promise.resolve({ data: {}, error: null });
    });
    const wrapper = render();
    await flushPromises();

    await wrapper.findAll("button").find(b => b.text() === "See all")!.trigger("click");
    await flushPromises();
    expect(api.list).toHaveBeenLastCalledWith("r-1", 1, -1);
    const rows = () => wrapper.findAll(".read-feedback-dialog__list > .read-feedback__entry");
    expect(rows()).toHaveLength(4);

    await rows()[0]!.findAll("button").find(b => b.text() === "Delete")!.trigger("click");
    expect(wrapper.find(".confirm-stub").text()).toContain("Delete this entry?");
    expect(api.remove).not.toHaveBeenCalled();

    await wrapper.find(".confirm-stub button").trigger("click");
    await flushPromises();

    expect(api.remove).toHaveBeenCalledWith(all[0]!.id);
    expect(rows()).toHaveLength(3);
    expect(entries(wrapper).map(e => e.find(".read-feedback__verdict").text())).toEqual([
      "Not again",
      "It was fine",
      "It was fine",
    ]);
    wrapper.unmount();
  });
});
