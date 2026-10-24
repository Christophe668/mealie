<template>
  <v-app class="ds-shell">
    <TheSnackbar />
    <AnnouncementDialog v-if="loggedIn" v-model="announcementsOpen" />

    <div class="ds-shell__frame">
      <AppShellRail
        class="ds-desktop-only"
        :brand-name="brandName"
        :home-to="todayPath"
        :items="primaryItems"
        :secondary-items="secondaryItems"
        :user-name="loggedIn ? auth.user.value?.fullName || '' : undefined"
        :announcement-count="announcementCount"
        @open-announcements="announcementsOpen = true"
        @log-out="auth.signOut('/login?direct=1')"
      />

      <div class="ds-shell__column">
        <AppShellTopBar
          :brand-name="brandName"
          :home-to="todayPath"
          :settings-to="loggedIn ? SETTINGS_PATH : undefined"
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
      :route-path="route.path"
    />
  </v-app>
</template>

<script setup lang="ts">
import AppShellRail from "./AppShellRail.vue";
import AppShellTabBar from "./AppShellTabBar.vue";
import AppShellTopBar from "./AppShellTopBar.vue";
import TheSnackbar from "~/components/Layout/LayoutParts/TheSnackbar.vue";
import AnnouncementDialog from "~/components/Domain/Announcement/AnnouncementDialog.vue";
import { useMealieAuth } from "~/composables/use-mealie-auth";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { useAnnouncements } from "~/composables/use-announcements";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import type { AppShellNavItem } from "~/types/application-types";

const PLAN_PATH = "/household/mealplan/planner/view";
const SHOP_PATH = "/shopping-lists";
const CONNECTIONS_PATH = "/user/connections";
const SETTINGS_PATH = "/user/profile";

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
// The recipe explorer still lives on the group index; Task 3 moves it to /g/:slug/recipes and
// only this line (plus the search target, which follows it) has to change.
const recipesPath = computed(() => todayPath.value);

function isUnder(prefix: string) {
  return route.path === prefix || route.path.startsWith(`${prefix}/`);
}

const recipesActive = computed(() => {
  const group = todayPath.value;
  return ["recipes", "r", "cookbooks"].some(section => isUnder(`${group}/${section}`));
});

const primaryItems = computed<AppShellNavItem[]>(() => {
  const items: AppShellNavItem[] = [
    {
      key: "today",
      label: i18n.t("app-shell.today"),
      to: todayPath.value,
      icon: "home",
      active: route.path.replace(/\/$/, "") === todayPath.value,
    },
    {
      key: "recipes",
      label: i18n.t("app-shell.recipes"),
      to: recipesPath.value,
      icon: "silverwareForkKnife",
      active: recipesActive.value,
    },
  ];
  if (isOwnGroup.value) {
    items.push(
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
    );
  }
  return items;
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

const addItems = computed<Omit<AppShellNavItem, "active">[]>(() => {
  if (!isOwnGroup.value) {
    return [];
  }
  return [
    { key: "recipe", label: i18n.t("app-shell.add-recipe-from-url"), to: `${todayPath.value}/r/create/url`, icon: "link" },
    { key: "plan", label: i18n.t("app-shell.add-to-plan"), to: "/household/mealplan/planner/edit", icon: "calendar" },
    { key: "list", label: i18n.t("app-shell.add-to-shopping-list"), to: SHOP_PATH, icon: "formatListCheck" },
  ];
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
    padding: calc(var(--ds-space) * 2) calc(var(--ds-space) * 2) calc(var(--ds-space) * 12);
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
