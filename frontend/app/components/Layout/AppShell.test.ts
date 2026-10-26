import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { reactive, ref } from "vue";
import AppShell from "./AppShell.vue";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  signOut: vi.fn(),
  loggedIn: { value: true },
  admin: { value: false },
  groupSlug: { value: "home" as string | undefined },
  announcementsEnabled: { value: false },
  unread: { value: [] as object[] },
  aiEnabled: { value: false },
}));

vi.mock("~/composables/use-mealie-auth", async () => {
  const { computed, ref } = await import("vue");
  return {
    useMealieAuth: () => ({
      user: ref({ id: "u1", fullName: "Christophe", groupSlug: mocks.groupSlug.value, admin: mocks.admin.value }),
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
  return {
    useAnnouncements: () => ({
      announcementsEnabled: ref(mocks.announcementsEnabled.value),
      newAnnouncements: ref(mocks.unread.value),
    }),
  };
});
vi.mock("~/composables/use-groups", async () => {
  const { computed } = await import("vue");
  return {
    useGroupSelf: () => ({
      group: computed(() => ({ aiProviderSettings: { aiEnabled: mocks.aiEnabled.value } })),
    }),
  };
});
vi.mock("~/components/global/LanguageDialog.vue", async () => {
  const { defineComponent, h } = await import("vue");
  return {
    default: defineComponent({
      props: { modelValue: Boolean },
      setup: props => () => h("div", { "class": "language-dialog", "data-open": String(props.modelValue) }),
    }),
  };
});
// Node 25 exposes a stub global localStorage that warns on access; the theme choice only needs an in-memory ref here.
vi.mock("@vueuse/core", async (importOriginal) => {
  const { ref } = await import("vue");
  return { ...(await importOriginal<object>()), useStorage: (_key: string, initial: unknown) => ref(initial) };
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
    mocks.admin.value = false;
    mocks.groupSlug.value = "home";
    mocks.announcementsEnabled.value = false;
    mocks.unread.value = [];
    mocks.aiEnabled.value = false;
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
    expect(link(wrapper, ".ds-rail", "Recipes").attributes("href")).toBe("/g/home/recipes");
    expect(link(wrapper, ".ds-rail", "Plan").attributes("href")).toBe("/household/mealplan/planner/view");
    expect(link(wrapper, ".ds-rail", "Shop").attributes("href")).toBe("/shopping-lists");
    expect(link(wrapper, ".ds-rail", "Pantry").attributes("href")).toBe("/household/pantry");
    expect(link(wrapper, ".ds-rail", "Connections").attributes("href")).toBe("/user/connections");
    expect(link(wrapper, ".ds-rail", "Settings").attributes("href")).toBe("/user/profile");
    expect(wrapper.find(".ds-rail").text()).toContain("Christophe");
  });

  test("the rail puts Pantry right after Shop and marks it on pantry pages", async () => {
    route.path = "/household/pantry";
    const wrapper = render();

    const labels = wrapper.findAll(".ds-rail nav").at(0)!.findAll("a").map(a => a.text().trim());
    expect(labels).toEqual(["Today", "Recipes", "Plan", "Shop", "Pantry"]);
    expect(link(wrapper, ".ds-rail", "Pantry").attributes("aria-current")).toBe("page");
    expect(link(wrapper, ".ds-rail", "Shop").attributes("aria-current")).toBeUndefined();
  });

  test("the tab bar carries the five primary destinations, Pantry included", async () => {
    route.path = "/household/pantry";
    const wrapper = render();

    const labels = wrapper.findAll(".ds-tabbar a").map(a => a.text().trim());
    expect(labels).toEqual(["Today", "Recipes", "Plan", "Shop", "Pantry"]);
    expect(link(wrapper, ".ds-tabbar", "Pantry").attributes("href")).toBe("/household/pantry");
    expect(link(wrapper, ".ds-tabbar", "Pantry").attributes("aria-current")).toBe("page");
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

    expect(mocks.push).toHaveBeenCalledWith({ path: "/g/home/recipes", query: { search: "chicken" } });
  });

  test("an empty search does nothing", async () => {
    const wrapper = render();

    await wrapper.find("form[role=search]").trigger("submit");
    expect(mocks.push).not.toHaveBeenCalled();
  });

  test("the add button opens a menu and Escape closes it, returning focus", async () => {
    const wrapper = render();
    const trigger = wrapper.find(".ds-shell__fab button[aria-haspopup=menu]");

    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(wrapper.find("[role=menu]").exists()).toBe(false);

    await trigger.trigger("click");
    const items = wrapper.findAll("[role=menu] [role=menuitem]");
    expect(trigger.attributes("aria-expanded")).toBe("true");
    expect(items.map(i => i.text().trim())).toEqual([
      "Add recipe from URL",
      "Create recipe",
      "Add to plan",
      "Add to shopping list",
      "Add to pantry",
    ]);
    expect(items.map(i => i.attributes("href"))).toEqual([
      "/g/home/r/create/url",
      "/g/home/r/create/new",
      "/household/mealplan/planner/view",
      "/shopping-lists",
      "/household/pantry?add=1",
    ]);
    expect(document.activeElement).toBe(items[0]!.element);

    await wrapper.find("[role=menu]").trigger("keydown", { key: "Escape" });
    expect(wrapper.find("[role=menu]").exists()).toBe(false);
    expect(document.activeElement).toBe(trigger.element);
  });

  test("arrow keys move through the add menu", async () => {
    const wrapper = render();
    await wrapper.find(".ds-shell__fab button[aria-haspopup=menu]").trigger("click");
    const menu = wrapper.find("[role=menu]");
    const items = wrapper.findAll("[role=menuitem]");

    await menu.trigger("keydown", { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]!.element);
    await menu.trigger("keydown", { key: "ArrowUp" });
    await menu.trigger("keydown", { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[4]!.element);
  });

  test("visitors see neither household pages nor the add button", () => {
    mocks.loggedIn.value = false;
    const wrapper = render();

    const labels = wrapper.findAll(".ds-tabbar a").map(a => a.text().trim());
    expect(labels).toEqual(["Recipes"]);
    expect(wrapper.find(".ds-shell__fab button[aria-haspopup=menu]").exists()).toBe(false);
    expect(wrapper.find(".ds-rail").text()).not.toContain("Connections");
    expect(wrapper.find(".ds-rail").text()).not.toContain("Pantry");
    expect(wrapper.find(".ds-rail").text()).toContain("Log in");
  });

  test("mobile floats its add button above the tab bar; desktop has its own in the top bar", async () => {
    const wrapper = render();
    const trigger = wrapper.find(".ds-topbar__add button[aria-haspopup=menu]");

    expect(wrapper.find(".ds-shell__fab").classes()).toContain("ds-mobile-only");
    expect(wrapper.find(".ds-topbar__add").classes()).toContain("ds-desktop-only");
    expect(wrapper.find(".ds-tabbar button").exists()).toBe(false);

    await trigger.trigger("click");
    expect(wrapper.findAll("[role=menu] [role=menuitem]").map(i => i.text().trim())).toEqual([
      "Add recipe from URL",
      "Create recipe",
      "Add to plan",
      "Add to shopping list",
      "Add to pantry",
    ]);
  });

  test.each([
    ["a shopping list", "/shopping-lists/abc"],
    ["the pantry", "/household/pantry"],
    ["a recipe", "/g/home/r/roast-chicken"],
    ["the recipe editor", "/g/home/r/roast-chicken/edit"],
  ])("the floating add button stays off %s, which pins its own action there", (_page, path) => {
    route.path = path;
    const wrapper = render();

    expect(wrapper.find(".ds-shell__fab").exists()).toBe(false);
    expect(wrapper.find(".ds-shell").classes()).not.toContain("ds-shell--fab");
  });

  test("the shopping lists overview keeps the floating add button", () => {
    route.path = "/shopping-lists";
    const wrapper = render();

    expect(wrapper.find(".ds-shell__fab").exists()).toBe(true);
    expect(wrapper.find(".ds-shell").classes()).toContain("ds-shell--fab");
  });

  test("the add menu leaves out group links until the group is known", async () => {
    mocks.groupSlug.value = undefined;
    route.path = "/";
    route.params = {};
    const wrapper = render();

    await wrapper.find(".ds-shell__fab button[aria-haspopup=menu]").trigger("click");
    const hrefs = wrapper.findAll("[role=menuitem]").map(i => i.attributes("href"));
    expect(hrefs).toEqual(["/household/mealplan/planner/view", "/shopping-lists", "/household/pantry?add=1"]);
    expect(link(wrapper, ".ds-rail", "Today").attributes("aria-current")).toBe("page");
  });

  const userTriggers = {
    "rail": ".ds-rail button[aria-haspopup=menu]",
    "mobile top bar": ".ds-topbar .ds-mobile-only button[aria-haspopup=menu]",
  };

  test.each(Object.entries(userTriggers))("the user menu opens from the %s", async (_where, selector) => {
    const wrapper = render();
    const trigger = wrapper.find(selector);

    await trigger.trigger("click");
    const labels = wrapper.findAll("[role=menu] li > *").map(i => i.text().trim());
    expect(labels).toEqual(["Profile", "Household", "Language", "Light theme", "Dark theme", "Match system theme", "Log out"]);

    await wrapper.find("[role=menu]").trigger("keydown", { key: "Escape" });
    expect(wrapper.find("[role=menu]").exists()).toBe(false);
    expect(document.activeElement).toBe(trigger.element);
  });

  test("the user menu links the Household page", async () => {
    const wrapper = render();

    await wrapper.find(userTriggers.rail).trigger("click");
    const household = wrapper.findAll("[role=menuitem]").find(i => i.text().trim() === "Household");
    expect(household?.attributes("href")).toBe("/household/profile");
  });

  test("admins also get the admin link", async () => {
    mocks.admin.value = true;
    const wrapper = render();

    await wrapper.find(userTriggers.rail).trigger("click");
    const admin = wrapper.findAll("[role=menuitem]").find(i => i.text().trim() === "Admin");
    expect(admin?.attributes("href")).toBe("/admin/site-settings");
  });

  function menuButton(wrapper: ReturnType<typeof render>, label: string) {
    const match = wrapper.findAll("[role=menu] button").find(b => b.text().trim() === label);
    if (!match) {
      throw new Error(`No "${label}" menu item`);
    }
    return match;
  }

  test("log out signs out", async () => {
    mocks.signOut.mockResolvedValue(undefined);
    const wrapper = render();

    await wrapper.find(userTriggers["mobile top bar"]).trigger("click");
    await menuButton(wrapper, "Log out").trigger("click");
    expect(mocks.signOut).toHaveBeenCalledWith("/login?direct=1");
  });

  test("a failed log out is caught", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    mocks.signOut.mockRejectedValue(new Error("offline"));
    const wrapper = render();

    await wrapper.find(userTriggers.rail).trigger("click");
    await menuButton(wrapper, "Log out").trigger("click");
    await flushPromises();
    expect(error).toHaveBeenCalled();
    error.mockRestore();
  });

  test("language opens the language dialog", async () => {
    const wrapper = render();
    expect(wrapper.find(".language-dialog").attributes("data-open")).toBe("false");

    await wrapper.find(userTriggers.rail).trigger("click");
    await menuButton(wrapper, "Language").trigger("click");
    expect(wrapper.find(".language-dialog").attributes("data-open")).toBe("true");
  });

  test("the theme choice is a radio group that remembers the pick", async () => {
    const wrapper = render();
    await wrapper.find(userTriggers.rail).trigger("click");

    expect(menuButton(wrapper, "Match system theme").attributes("role")).toBe("menuitemradio");
    await menuButton(wrapper, "Dark theme").trigger("click");
    await wrapper.find(userTriggers.rail).trigger("click");

    expect(menuButton(wrapper, "Dark theme").attributes("aria-checked")).toBe("true");
    expect(menuButton(wrapper, "Light theme").attributes("aria-checked")).toBe("false");
    await menuButton(wrapper, "Match system theme").trigger("click");
  });

  test("announcements stay reachable; the count shows only when something is unread", async () => {
    mocks.announcementsEnabled.value = true;
    const wrapper = render();
    const item = wrapper.findAll(".ds-rail button").find(b => b.text().includes("Announcements"));
    expect(item?.find(".ds-rail__count").exists()).toBe(false);

    wrapper.unmount();
    mocks.unread.value = [{ key: "a" }];
    const withUnread = render();
    const unreadItem = withUnread.findAll(".ds-rail button").find(b => b.text().includes("Announcements"));
    expect(unreadItem?.find(".ds-rail__count").text()).toBe("1");
  });

  test("the add menu offers the AI importer when the group has AI enabled", async () => {
    mocks.aiEnabled.value = true;
    const wrapper = render();

    await wrapper.find(".ds-shell__fab button[aria-haspopup=menu]").trigger("click");
    const ai = wrapper.findAll("[role=menuitem]").find(i => i.text().trim() === "Import with AI");
    expect(ai?.attributes("href")).toBe("/g/home/r/create/ai");
  });

  test("the mobile menu carries announcements with the unread count", async () => {
    mocks.announcementsEnabled.value = true;
    mocks.unread.value = [{ key: "a" }, { key: "b" }];
    const wrapper = render();

    await wrapper.find(userTriggers["mobile top bar"]).trigger("click");
    const labels = wrapper.findAll("[role=menu] li > *").map(i => i.text().replace(/\s+/g, " ").trim());
    expect(labels).toEqual(["Profile", "Household", "Announcements 2", "Language", "Light theme", "Dark theme", "Match system theme", "Log out"]);
    expect(menuButton(wrapper, "Announcements 2").find(".ds-menu__badge").text()).toBe("2");
  });

  test("visitors on mobile get Log in, language and theme from the top bar menu", async () => {
    mocks.loggedIn.value = false;
    const wrapper = render();

    await wrapper.find(userTriggers["mobile top bar"]).trigger("click");
    const labels = wrapper.findAll("[role=menu] li > *").map(i => i.text().trim());
    expect(labels).toEqual(["Log in", "Language", "Light theme", "Dark theme", "Match system theme"]);
    expect(wrapper.findAll("[role=menuitem]").find(i => i.text().trim() === "Log in")?.attributes("href")).toBe("/login");

    await menuButton(wrapper, "Language").trigger("click");
    expect(wrapper.find(".language-dialog").attributes("data-open")).toBe("true");
  });

  test("account links sit in their own navigation landmark", () => {
    const wrapper = render();

    const account = wrapper.find(".ds-rail nav[aria-label=Account]");
    expect(account.text()).toContain("Connections");
    expect(account.text()).toContain("Settings");
  });

  test("the search shortcut is left alone while typing in another field", () => {
    const wrapper = render();
    const other = document.createElement("textarea");
    document.body.appendChild(other);
    other.focus();

    const event = new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true, cancelable: true });
    other.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(other);
    expect(wrapper.find("input[type=search]").exists()).toBe(true);
  });
});
