<template>
  <div>
    <!-- Cookbooks have no rail entry; they hang off the Recipes page instead. -->
    <div class="recipes-links">
      <DsButton variant="line" icon="pages" :to="`/g/${groupSlug}/cookbooks`">
        {{ $t("cookbook.cookbooks") }}
      </DsButton>
    </div>
    <RecipeExplorerPage />
  </div>
</template>

<script setup lang="ts">
import DsButton from "~/components/Design/DsButton.vue";
import RecipeExplorerPage from "~/components/Domain/Recipe/RecipeExplorerPage/RecipeExplorerPage.vue";
import { useAppShellTitle } from "~/composables/use-app-shell-title";

const i18n = useI18n();
const route = useRoute();
const groupSlug = computed(() => route.params.groupSlug as string);
useAppShellTitle(() => i18n.t("app-shell.recipes"));
</script>

<style scoped>
.recipes-links {
  display: flex;
  justify-content: flex-end;
  padding: 0 calc(var(--ds-space) * 1.5);
}
</style>
