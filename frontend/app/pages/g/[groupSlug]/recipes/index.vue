<template>
  <div>
    <RecipeExplorerPage />
  </div>
</template>

<script setup lang="ts">
import RecipeExplorerPage from "~/components/Domain/Recipe/RecipeExplorerPage/RecipeExplorerPage.vue";
import { useAppShellTitle } from "~/composables/use-app-shell-title";

const i18n = useI18n();
useAppShellTitle(() => i18n.t("app-shell.recipes"));
</script>
