import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ref } from "vue";
import type { MemberProfileOut } from "~/lib/api/types/household";

// The page wires the profile composable to the cards; the composable is a stand-in here.
const profile = vi.hoisted(() => ({ current: null as any }));

vi.mock("~/composables/use-household-profile", () => ({ useHouseholdProfile: () => profile.current }));
vi.mock("~/composables/use-mealie-auth", async () => {
  const { ref } = await import("vue");
  return { useMealieAuth: () => ({ user: ref({ id: "u1", fullName: "Christophe", username: "christophe" }) }) };
});
vi.mock("~/composables/use-households", async () => {
  const { ref } = await import("vue");
  return { useHouseholdSelf: () => ({ household: ref({ preferences: { firstDayOfWeek: 1 } }) }) };
});

const stubs = {
  "v-icon": { template: "<i />" },
  "v-card-text": { template: "<div><slot /></div>" },
  "BaseDialog": {
    props: ["modelValue", "title"],
    emits: ["confirm", "update:modelValue"],
    template: "<div v-if=\"modelValue\" class=\"confirm-stub\"><p>{{ title }}</p><slot /><button class=\"confirm\" @click=\"$emit('confirm'); $emit('update:modelValue', false)\">Confirm</button></div>",
  },
};

const sam: MemberProfileOut = { id: "sam", groupId: "g", householdId: "h", name: "Sam", userId: null, allergies: ["peanuts"], position: 0 };

function fakeProfile(members: MemberProfileOut[] = []) {
  return {
    members: ref(members),
    preferences: ref(null),
    loading: ref(false),
    failed: ref(false),
    loaded: ref(true),
    refresh: vi.fn(),
    createMember: vi.fn(async (data: object) => ({ id: "new", groupId: "g", householdId: "h", ...data })),
    updateMember: vi.fn(),
    removeMember: vi.fn().mockResolvedValue(true),
    savePreferences: vi.fn(),
  };
}

async function render() {
  const { default: Page } = await import("~/pages/household/profile.vue");
  return mount(Page, {
    global: { stubs, mocks: { $globals: { icons: { alertCircle: "" } } } },
    attachTo: document.body,
  });
}

const button = (wrapper: Awaited<ReturnType<typeof render>>, label: string) =>
  wrapper.findAll("button").find(b => b.text().trim() === label);

beforeEach(() => {
  vi.stubGlobal("definePageMeta", () => {});
  vi.stubGlobal("useSeoMeta", () => {});
  vi.stubGlobal("useRoute", () => ({ path: "/household/profile", params: {}, query: {} }));
  vi.stubGlobal("useState", (_key: string, init: () => unknown) => ref(init()));
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("household page", () => {
  test("the empty state's Add yourself prefills the user's name and links the profile", async () => {
    profile.current = fakeProfile();
    const wrapper = await render();

    expect(wrapper.text()).toContain("Tell Claude who’s eating");
    await button(wrapper, "Add yourself")!.trigger("click");

    const name = wrapper.find<HTMLInputElement>(".profile-member input[type=text]");
    expect(name.element.value).toBe("Christophe");
    expect(wrapper.find(".profile-member").text()).toContain("You");

    await wrapper.find(".profile-member form").trigger("submit");
    await flushPromises();
    expect(profile.current.createMember).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ name: "Christophe", userId: "u1", position: 0 }),
    );
  });

  test("Remove asks first, and only removes once confirmed", async () => {
    profile.current = fakeProfile([sam]);
    const wrapper = await render();

    expect(wrapper.text()).not.toContain("Tell Claude who’s eating");
    await button(wrapper, "Remove")!.trigger("click");
    expect(wrapper.find(".confirm-stub").text()).toContain("Remove Sam?");
    expect(profile.current.removeMember).not.toHaveBeenCalled();

    await wrapper.find(".confirm").trigger("click");
    await flushPromises();
    expect(profile.current.removeMember).toHaveBeenCalledExactlyOnceWith("sam");
  });

  test("a new person goes after the others and an unsaved card is dropped without asking", async () => {
    profile.current = fakeProfile([sam]);
    const wrapper = await render();

    await button(wrapper, "Add a person")!.trigger("click");
    expect(wrapper.findAll(".profile-member")).toHaveLength(2);
    await wrapper.findAll(".profile-member").at(1)!.findAll("button").find(b => b.text() === "Remove")!.trigger("click");
    expect(wrapper.findAll(".profile-member")).toHaveLength(1);
    expect(wrapper.find(".confirm-stub").exists()).toBe(false);

    await button(wrapper, "Add a person")!.trigger("click");
    await wrapper.findAll(".profile-member").at(1)!.find("input[type=text]").setValue("Kim");
    await wrapper.findAll(".profile-member").at(1)!.find("form").trigger("submit");
    await flushPromises();
    expect(profile.current.createMember).toHaveBeenCalledWith(expect.objectContaining({ name: "Kim", position: 1 }));
  });

  test("the habits follow the household's first day of the week", async () => {
    profile.current = fakeProfile([sam]);
    const wrapper = await render();

    const days = wrapper.findAll(".profile-weekdays button").map(b => b.text().trim());
    expect(days[0]).toBe("Mon");
  });
});
