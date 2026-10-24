<template>
  <div>
    <!-- The old sidebar's recipe destinations: cookbooks, organizers, favourites, timeline and the finder. -->
    <nav class="recipes-links" :aria-label="$t('recipes-links.label')">
      <DsButton
        v-for="link in links"
        :key="link.key"
        variant="line"
        :icon="link.icon"
        :to="link.to"
      >
        {{ link.label }}
      </DsButton>
    </nav>
    <RecipeExplorerPage />
  </div>
</template>

<script setup lang="ts">
import DsButton from "~/components/Design/DsButton.vue";
import RecipeExplorerPage from "~/components/Domain/Recipe/RecipeExplorerPage/RecipeExplorerPage.vue";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import type { Icon } from "~/lib/icons/icon-type";

const i18n = useI18n();
const route = useRoute();
const auth = useMealieAuth();
const { isOwnGroup } = useLoggedInState();
const groupSlug = computed(() => route.params.groupSlug as string);
useAppShellTitle(() => i18n.t("app-shell.recipes"));

const links = computed(() => {
  const base = `/g/${groupSlug.value}`;
  const items: { key: string; label: string; icon: keyof Icon; to: string }[] = [
    { key: "cookbooks", label: i18n.t("recipes-links.cookbooks"), icon: "pages", to: `${base}/cookbooks` },
    { key: "categories", label: i18n.t("recipes-links.categories"), icon: "categories", to: `${base}/recipes/categories` },
    { key: "tags", label: i18n.t("recipes-links.tags"), icon: "tags", to: `${base}/recipes/tags` },
    { key: "tools", label: i18n.t("recipes-links.tools"), icon: "tools", to: `${base}/recipes/tools` },
  ];
  const userId = auth.user.value?.id;
  if (isOwnGroup.value && userId) {
    items.push({ key: "favourites", label: i18n.t("recipes-links.favourites"), icon: "heartOutline", to: `/user/${userId}/favorites` });
  }
  items.push(
    { key: "timeline", label: i18n.t("recipes-links.timeline"), icon: "timelineText", to: `${base}/recipes/timeline` },
    { key: "finder", label: i18n.t("recipes-links.finder"), icon: "potSteam", to: `${base}/recipes/finder` },
  );
  return items;
});
</script>

<style scoped>
.recipes-links {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
  margin-bottom: calc(var(--ds-space) * 2);
}

@media (max-width: 599px) {
  /* One scrollable row on phones rather than four wrapped lines of buttons. */
  .recipes-links {
    flex-wrap: nowrap;
    margin-inline: calc(var(--ds-space) * -2);
    padding-inline: calc(var(--ds-space) * 2);
    overflow-x: auto;
    scrollbar-width: none;
  }
}
</style>
