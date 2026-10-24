<!-- The week view is a page of its own; the edit tab still lives inside the classic planner. -->
<template>
  <NuxtPage v-if="isView" />
  <MealPlanClassicPlanner v-else />
</template>

<script setup lang="ts">
import MealPlanClassicPlanner from "~/components/Domain/Mealplan/MealPlanClassicPlanner.vue";

definePageMeta({
  middleware: ["auth"],
});

const VIEW = "household-mealplan-planner-view";

const route = useRoute();
const router = useRouter();

// Force to /view if current route is /planner
if (route.path === "/household/mealplan/planner") {
  router.push({
    name: VIEW,
    query: route.query,
  });
}

const isView = computed(() => route.name === VIEW || route.path === "/household/mealplan/planner");
</script>
