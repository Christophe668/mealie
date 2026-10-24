import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { reactive, ref } from "vue";
import AppShell from "./AppShell.vue";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  signOut: vi.fn(),
  loggedIn: { value: true },
}));

vi.mock("~/composables/use-mealie-auth", async () => {
  const { computed, ref } = await import("vue");
  return {
    useMealieAuth: () => ({
      user: ref({ id: "u1", fullName: "Christophe", groupSlug: "home" }),
      loggedIn: computed(() => mocks.loggedIn.value),
      signOut: mocks.signOut,
    }),
  };
});
vi.mock("~/composables/use-logged-in-state", async () => {
  const { computed } = await import("vue");
  return {
    useLoggedInState: () => ({
      loggedIn: computed(() => mocks.loggedIn.value),
      isOwnGroup: computed(() => mocks.loggedIn.value),
    }),
  };
});
vi.mock("~/composables/use-announcements", async () => {
  const { ref } = await import("vue");
  return { useAnnouncements: () => ({ announcementsEnabled: ref(false), newAnnouncements: ref([]) }) };
});
vi.mock("~/components/Layout/LayoutParts/TheSnackbar.vue", () => ({ default: { render: () => null } }));
vi.mock("~/components/Domain/Announcement/AnnouncementDialog.vue", () => ({ default: { render: () => null } }));

// Nuxt registers NuxtLink and Vuetify registers v-icon at runtime; plain stand-ins keep the markup inspectable.
const stubs = {
  "v-app": { template: "<div class=\"v-application\"><slot /></div>" },
  "NuxtLink": { props: ["to"], template: "<a :href=\"to\"><slot /></a>" },
  "v-icon": { props: ["icon"], template: "<i class=\"v-icon\" aria-hidden=\"true\" />" },
};

const route = reactive({ path: "/g/home", params: { groupSlug: "home" } as Record<string, string> });

function render() {
  return mount(AppShell, {
    slots: { default: "<p class=\"page\">Page content</p>" },
    global: { stubs },
    attachTo: document.body,
  });
}

function link(wrapper: ReturnType<typeof render>, region: string, label: string) {
  const match = wrapper.findAll(`${region} a`).find(a => a.text().trim() === label);
  if (!match) {
    throw new Error(`No "${label}" link in ${region}`);
  }
  return match;
}

describe("AppShell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.loggedIn.value = true;
    route.path = "/g/home";
    route.params = { groupSlug: "home" };
    vi.stubGlobal("useRoute", () => route);
    vi.stubGlobal("useRouter", () => ({ push: mocks.push }));
    vi.stubGlobal("useState", (_key: string, init: () => unknown) => ref(init()));
    vi.stubGlobal("useNuxtApp", () => ({ $appInfo: { brandingName: "Mealie" } }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  test("renders the page inside the main column", () => {
    const wrapper = render();

    expect(wrapper.find("main.ds-main .page").exists()).toBe(true);
  });

  test("the rail links every destination to its route", () => {
    const wrapper = render();

    expect(link(wrapper, ".ds-rail", "Today").attributes("href")).toBe("/g/home");
    expect(link(wrapper, ".ds-rail", "Recipes").attributes("href")).toBe("/g/home");
    expect(link(wrapper, ".ds-rail", "Plan").attributes("href")).toBe("/household/mealplan/planner/view");
    expect(link(wrapper, ".ds-rail", "Shop").attributes("href")).toBe("/shopping-lists");
    expect(link(wrapper, ".ds-rail", "Connections").attributes("href")).toBe("/user/connections");
    expect(link(wrapper, ".ds-rail", "Settings").attributes("href")).toBe("/user/profile");
    expect(wrapper.find(".ds-rail").text()).toContain("Christophe");
  });

  test("the tab bar carries the four primary destinations", () => {
    const wrapper = render();

    const labels = wrapper.findAll(".ds-tabbar a").map(a => a.text().trim());
    expect(labels).toEqual(["Today", "Recipes", "Plan", "Shop"]);
  });

  test("marks only the active destination with aria-current=page", () => {
    const wrapper = render();

    expect(link(wrapper, ".ds-rail", "Today").attributes("aria-current")).toBe("page");
    expect(link(wrapper, ".ds-tabbar", "Today").attributes("aria-current")).toBe("page");
    for (const label of ["Recipes", "Plan", "Shop", "Connections", "Settings"]) {
      expect(link(wrapper, ".ds-rail", label).attributes("aria-current")).toBeUndefined();
    }
  });

  test("follows the route to nested pages", async () => {
    const wrapper = render();
    route.path = "/shopping-lists/abc";
    await flushPromises();

    expect(link(wrapper, ".ds-rail", "Shop").attributes("aria-current")).toBe("page");
    expect(link(wrapper, ".ds-tabbar", "Shop").attributes("aria-current")).toBe("page");
    expect(link(wrapper, ".ds-rail", "Today").attributes("aria-current")).toBeUndefined();

    route.path = "/g/home/r/roast-chicken";
    await flushPromises();
    expect(link(wrapper, ".ds-rail", "Recipes").attributes("aria-current")).toBe("page");
  });

  test("the rail is desktop-only and the tab bar mobile-only", () => {
    const wrapper = render();

    expect(wrapper.find(".ds-rail").classes()).toContain("ds-desktop-only");
    expect(wrapper.find(".ds-tabbar").classes()).toContain("ds-mobile-only");
  });

  test.each([
    { metaKey: true, ctrlKey: false },
    { metaKey: false, ctrlKey: true },
  ])("the keyboard shortcut focuses search (%o)", (modifiers) => {
    const wrapper = render();

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ...modifiers }));
    expect(document.activeElement).toBe(wrapper.find("input[type=search]").element);
  });

  test("submitting search opens the recipe explorer with the query", async () => {
    const wrapper = render();

    await wrapper.find("input[type=search]").setValue("  chicken  ");
    await wrapper.find("form[role=search]").trigger("submit");

    expect(mocks.push).toHaveBeenCalledWith({ path: "/g/home", query: { search: "chicken" } });
  });

  test("an empty search does nothing", async () => {
    const wrapper = render();

    await wrapper.find("form[role=search]").trigger("submit");
    expect(mocks.push).not.toHaveBeenCalled();
  });

  test("the add button opens a menu and Escape closes it, returning focus", async () => {
    const wrapper = render();
    const trigger = wrapper.find(".ds-tabbar button[aria-haspopup=menu]");

    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(wrapper.find("[role=menu]").exists()).toBe(false);

    await trigger.trigger("click");
    const items = wrapper.findAll("[role=menu] [role=menuitem]");
    expect(trigger.attributes("aria-expanded")).toBe("true");
    expect(items.map(i => i.text().trim())).toEqual(["Add recipe from URL", "Add to plan", "Add to shopping list"]);
    expect(items[0]!.attributes("href")).toBe("/g/home/r/create/url");
    expect(document.activeElement).toBe(items[0]!.element);

    await wrapper.find("[role=menu]").trigger("keydown", { key: "Escape" });
    expect(wrapper.find("[role=menu]").exists()).toBe(false);
    expect(document.activeElement).toBe(trigger.element);
  });

  test("arrow keys move through the add menu", async () => {
    const wrapper = render();
    await wrapper.find(".ds-tabbar button[aria-haspopup=menu]").trigger("click");
    const menu = wrapper.find("[role=menu]");
    const items = wrapper.findAll("[role=menuitem]");

    await menu.trigger("keydown", { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]!.element);
    await menu.trigger("keydown", { key: "ArrowUp" });
    await menu.trigger("keydown", { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[2]!.element);
  });

  test("visitors see neither household pages nor the add button", () => {
    mocks.loggedIn.value = false;
    const wrapper = render();

    const labels = wrapper.findAll(".ds-tabbar a").map(a => a.text().trim());
    expect(labels).toEqual(["Today", "Recipes"]);
    expect(wrapper.find(".ds-tabbar button[aria-haspopup=menu]").exists()).toBe(false);
    expect(wrapper.find(".ds-rail").text()).not.toContain("Connections");
    expect(wrapper.find(".ds-rail").text()).toContain("Log in");
  });
});
