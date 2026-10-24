<template>
  <v-app class="ds-shell">
    <TheSnackbar />
    <AnnouncementDialog v-if="loggedIn" v-model="announcementsOpen" />
    <LanguageDialog v-model="languageOpen" />

    <div class="ds-shell__frame">
      <AppShellRail
        class="ds-desktop-only"
        :brand-name="brandName"
        :home-to="todayPath"
        :items="primaryItems"
        :secondary-items="secondaryItems"
        :user-name="loggedIn ? auth.user.value?.fullName || '' : undefined"
        :user-items="userItems"
        :show-announcements="loggedIn && announcementsEnabled"
        :announcement-count="announcementCount"
        @open-announcements="announcementsOpen = true"
      />

      <div class="ds-shell__column">
        <AppShellTopBar
          :brand-name="brandName"
          :home-to="todayPath"
          :add-items="addItems"
          :user-items="userItems"
          @search="search"
        >
          <template #title>
            <slot name="title">
              {{ pageTitle }}
            </slot>
          </template>
        </AppShellTopBar>

        <main class="ds-main">
          <slot />
        </main>
      </div>
    </div>

    <AppShellTabBar
      class="ds-mobile-only"
      :items="primaryItems"
      :add-items="addItems"
    />
  </v-app>
</template>

<script setup lang="ts">
import AppShellRail from "./AppShellRail.vue";
import AppShellTabBar from "./AppShellTabBar.vue";
import AppShellTopBar from "./AppShellTopBar.vue";
import TheSnackbar from "~/components/Layout/LayoutParts/TheSnackbar.vue";
import AnnouncementDialog from "~/components/Domain/Announcement/AnnouncementDialog.vue";
import LanguageDialog from "~/components/global/LanguageDialog.vue";
import { useStorage } from "@vueuse/core";
import { useMealieAuth } from "~/composables/use-mealie-auth";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { useAnnouncements } from "~/composables/use-announcements";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import type { AppShellMenuItem, AppShellNavItem } from "~/types/application-types";

const PLAN_PATH = "/household/mealplan/planner/view";
const SHOP_PATH = "/shopping-lists";
const CONNECTIONS_PATH = "/user/connections";
const SETTINGS_PATH = "/user/profile";
const ADMIN_PATH = "/admin/site-settings";
// The key the dark-mode plugin's useDark() persists to; writing it here switches the theme everywhere.
const COLOR_SCHEME_KEY = "vueuse-color-scheme";

const i18n = useI18n();
const route = useRoute();
const router = useRouter();
const auth = useMealieAuth();
const { loggedIn, isOwnGroup } = useLoggedInState();
const { announcementsEnabled, newAnnouncements } = useAnnouncements();
const pageTitle = useAppShellTitle();

const nuxtApp = useNuxtApp();
const brandName = computed(() => nuxtApp.$appInfo?.brandingName || "Mealie");

// Same resolution as DefaultLayout: the slug in the URL wins (public group pages), else the user's own group.
const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");
const todayPath = computed(() => (groupSlug.value ? `/g/${groupSlug.value}` : "/"));
// The group index is Home ("Today"); the recipe explorer lives under /recipes. Search follows it.
const recipesPath = computed(() => (groupSlug.value ? `/g/${groupSlug.value}/recipes` : "/"));

// "/g/home/" and "/g/home" are the same page; "/" stays "/".
const currentPath = computed(() => (route.path.length > 1 ? route.path.replace(/\/$/, "") : route.path));

function isUnder(prefix: string) {
  return currentPath.value === prefix || currentPath.value.startsWith(`${prefix}/`);
}

const recipesActive = computed(() => {
  const group = todayPath.value;
  return ["recipes", "r", "cookbooks"].some(section => isUnder(`${group}/${section}`));
});

const primaryItems = computed<AppShellNavItem[]>(() => {
  const recipes: AppShellNavItem = {
    key: "recipes",
    label: i18n.t("app-shell.recipes"),
    to: recipesPath.value,
    icon: "silverwareForkKnife",
    active: recipesActive.value,
  };
  // Today is the signed-in household's day; visitors of a public group only browse its recipes.
  if (!isOwnGroup.value) {
    return [recipes];
  }
  return [
    {
      key: "today",
      label: i18n.t("app-shell.today"),
      to: todayPath.value,
      icon: "home",
      active: currentPath.value === todayPath.value,
    },
    recipes,
    {
      key: "plan",
      label: i18n.t("app-shell.plan"),
      to: PLAN_PATH,
      icon: "calendar",
      active: isUnder("/household/mealplan"),
    },
    {
      key: "shop",
      label: i18n.t("app-shell.shop"),
      to: SHOP_PATH,
      icon: "cartCheck",
      active: isUnder(SHOP_PATH),
    },
  ];
});

const secondaryItems = computed<AppShellNavItem[]>(() => {
  if (!loggedIn.value) {
    return [];
  }
  return [
    {
      key: "connections",
      label: i18n.t("app-shell.connections"),
      to: CONNECTIONS_PATH,
      icon: "link",
      active: isUnder(CONNECTIONS_PATH),
    },
    {
      key: "settings",
      label: i18n.t("app-shell.settings"),
      to: SETTINGS_PATH,
      icon: "cog",
      active: isUnder(SETTINGS_PATH),
    },
  ];
});

const addItems = computed<AppShellMenuItem[]>(() => {
  if (!isOwnGroup.value) {
    return [];
  }
  const items: AppShellMenuItem[] = [];
  // Recipe creation lives under the group; without a slug yet (auth still loading) those links would be invalid.
  if (groupSlug.value) {
    items.push(
      { key: "recipe-url", label: i18n.t("app-shell.add-recipe-from-url"), to: `${todayPath.value}/r/create/url`, icon: "link" },
      { key: "recipe-new", label: i18n.t("app-shell.create-recipe"), to: `${todayPath.value}/r/create/new`, icon: "edit" },
    );
  }
  items.push(
    { key: "plan", label: i18n.t("app-shell.add-to-plan"), to: "/household/mealplan/planner/edit", icon: "calendar" },
    { key: "list", label: i18n.t("app-shell.add-to-shopping-list"), to: SHOP_PATH, icon: "formatListCheck" },
  );
  return items;
});

const languageOpen = ref(false);
const colorScheme = useStorage<"auto" | "light" | "dark">(COLOR_SCHEME_KEY, "auto");

async function logOut() {
  try {
    await auth.signOut("/login?direct=1");
  }
  catch (error) {
    console.error("Logout failed:", error);
  }
}

const userItems = computed<AppShellMenuItem[]>(() => {
  if (!loggedIn.value) {
    return [];
  }
  const items: AppShellMenuItem[] = [
    { key: "profile", label: i18n.t("app-shell.profile"), to: SETTINGS_PATH, icon: "user" },
  ];
  if (auth.user.value?.admin) {
    items.push({ key: "admin", label: i18n.t("app-shell.admin"), to: ADMIN_PATH, icon: "wrench" });
  }
  items.push(
    { key: "language", label: i18n.t("app-shell.language"), icon: "translate", onSelect: () => (languageOpen.value = true) },
    ...(["light", "dark", "auto"] as const).map((scheme, index) => ({
      key: `theme-${scheme}`,
      label: i18n.t(`app-shell.theme-${scheme}`),
      icon: ({ light: "weatherSunny", dark: "weatherNight", auto: "themeLightDark" } as const)[scheme],
      checked: colorScheme.value === scheme,
      dividerBefore: index === 0,
      onSelect: () => (colorScheme.value = scheme),
    })),
    { key: "log-out", label: i18n.t("app-shell.log-out"), icon: "logout", onSelect: logOut, dividerBefore: true },
  );
  return items;
});

const announcementsOpen = ref(false);
const announcementCount = computed(() => (announcementsEnabled.value ? newAnnouncements.value.length : 0));

function search(query: string) {
  router.push({ path: recipesPath.value, query: { search: query } });
}
</script>

<style scoped>
.ds-shell {
  --ds-shell-rail: 232px;
  --ds-shell-content: 1200px;

  background: var(--ds-bg);
  color: var(--ds-text);
}

.ds-shell__frame {
  display: grid;
  grid-template-columns: var(--ds-shell-rail) minmax(0, 1fr);
  min-height: 100vh;
}

.ds-shell__column {
  min-width: 0;
  max-width: var(--ds-shell-content);
  padding: calc(var(--ds-space) * 4) calc(var(--ds-space) * 5);
}

.ds-main {
  min-width: 0;
}

@media (max-width: 1023px) {
  .ds-shell__frame {
    grid-template-columns: minmax(0, 1fr);
  }

  .ds-shell__column {
    /* Bottom padding clears the floating tab bar. */
    padding: calc(var(--ds-space) * 2) calc(var(--ds-space) * 2)
      calc(var(--ds-space) * 12 + env(safe-area-inset-bottom));
  }
}
</style>

<style>
/* Shell visibility utilities. !important so they win over a component's own display rule. */
@media (max-width: 1023px) {
  .ds-desktop-only {
    display: none !important;
  }
}

@media (min-width: 1024px) {
  .ds-mobile-only {
    display: none !important;
  }
}

@media print {
  .ds-shell .ds-rail,
  .ds-shell .ds-tabbar,
  .ds-shell .ds-topbar__search {
    display: none !important;
  }
}
</style>
