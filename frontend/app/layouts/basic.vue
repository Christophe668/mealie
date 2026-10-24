<template>
  <v-app class="ds-basic">
    <TheSnackbar />
    <LanguageDialog v-model="languageOpen" />

    <!-- Minimal top bar for pages outside the shell (consent, password reset, shared recipes):
         the brand and the language and theme choices, nothing to navigate away to. -->
    <header class="ds-basic__bar d-print-none">
      <NuxtLink :to="homeTo" class="ds-basic__brand ds-focus">
        <img
          v-if="$appInfo.brandingLogoUrl"
          :src="$appInfo.brandingLogoUrl"
          alt=""
          class="ds-basic__logo"
        >
        <DsIcon v-else name="primary" :size="28" />
        {{ brandName }}
      </NuxtLink>

      <AppShellMenu
        :items="menuItems"
        :label="$t('app-shell.display-settings')"
        :trigger-label="$t('app-shell.display-settings')"
        trigger-class="ds-basic__icon ds-focus"
        placement="bottom-end"
      >
        <template #trigger>
          <DsIcon name="translate" :size="22" />
        </template>
      </AppShellMenu>
    </header>

    <v-main class="ds-basic__main">
      <NuxtPage />
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import { useStorage } from "@vueuse/core";
import DsIcon from "~/components/Design/DsIcon.vue";
import AppShellMenu from "~/components/Layout/AppShellMenu.vue";
import TheSnackbar from "~/components/Layout/LayoutParts/TheSnackbar.vue";
import LanguageDialog from "~/components/global/LanguageDialog.vue";
import { useGlobalI18n } from "~/composables/use-global-i18n";
import type { AppShellMenuItem } from "~/types/application-types";

// The key the dark-mode plugin's useDark() persists to (same as the app shell's theme items).
const COLOR_SCHEME_KEY = "vueuse-color-scheme";

const i18n = useGlobalI18n();
const route = useRoute();
const auth = useMealieAuth();
const nuxtApp = useNuxtApp();

const brandName = computed(() => nuxtApp.$appInfo?.brandingName || "Mealie");
const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");
const homeTo = computed(() => (groupSlug.value ? `/g/${groupSlug.value}` : "/"));

const languageOpen = ref(false);
const colorScheme = useStorage<"auto" | "light" | "dark">(COLOR_SCHEME_KEY, "auto");

const menuItems = computed<AppShellMenuItem[]>(() => [
  { key: "language", label: i18n.t("app-shell.language"), icon: "translate", onSelect: () => (languageOpen.value = true) },
  ...(["light", "dark", "auto"] as const).map((scheme, index) => ({
    key: `theme-${scheme}`,
    label: i18n.t(`app-shell.theme-${scheme}`),
    icon: ({ light: "weatherSunny", dark: "weatherNight", auto: "themeLightDark" } as const)[scheme],
    checked: colorScheme.value === scheme,
    dividerBefore: index === 0,
    onSelect: () => (colorScheme.value = scheme),
  })),
]);
</script>

<style scoped>
.ds-basic {
  background: var(--ds-bg);
  color: var(--ds-text);
}

.ds-basic__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: calc(var(--ds-space) * 2);
  padding: calc(var(--ds-space) * 2) calc(var(--ds-space) * 5);
  border-bottom: 1px solid var(--ds-border);
  background: var(--ds-surface);
}

.ds-basic__brand {
  display: inline-flex;
  align-items: center;
  gap: var(--ds-space);
  color: var(--ds-text);
  font-size: var(--ds-t-4);
  font-weight: 800;
  font-variation-settings: "wdth" 90;
  letter-spacing: -0.01em;
  text-decoration: none;
}

.ds-basic__logo {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.ds-basic__bar :deep(.ds-basic__icon) {
  display: grid;
  place-items: center;
  width: calc(var(--ds-space) * 5);
  height: calc(var(--ds-space) * 5);
  padding: 0;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  cursor: pointer;
}

.ds-basic__main {
  background: var(--ds-bg);
}

@media (max-width: 1023px) {
  .ds-basic__bar {
    padding: calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 2);
  }
}
</style>
