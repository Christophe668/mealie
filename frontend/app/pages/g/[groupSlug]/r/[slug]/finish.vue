<template>
  <div class="finish-page">
    <p v-if="!recipe" class="finish-page__status" role="status">
      <template v-if="notFound">
        <span>{{ $t("recipe-read.not-found") }}</span>
        <NuxtLink :to="homeTo" class="finish-page__link ds-focus">
          {{ $t("app-shell.today") }}
        </NuxtLink>
      </template>
      <span v-else class="ds-muted">{{ $t("recipe-read.loading") }}</span>
    </p>

    <template v-else>
      <NuxtLink :to="recipeTo" class="finish-page__recipe ds-focus">
        <span class="finish-page__photo">
          <img v-if="imageUrl && !imageFailed" :src="imageUrl" alt="" @error="imageFailed = true">
          <DsIcon v-else name="silverwareForkKnife" :size="22" />
        </span>
        <span class="finish-page__text">
          <span class="finish-page__name">{{ recipe.name }}</span>
          <span class="finish-page__day ds-muted">{{ dayLabel }}</span>
        </span>
      </NuxtLink>

      <CookFinish
        class="finish-page__finish"
        :recipe-id="recipe.id || ''"
        :back-to="homeTo"
        :logged-in="true"
        :scale="scale"
        :cooked-on="cookedOn"
        :meal-plan-entry-id="entryId"
        amend
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { differenceInCalendarDays, format, parseISO } from "date-fns";
import CookFinish from "~/components/Domain/Cook/CookFinish.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { useStaticRoutes } from "~/composables/api";
import { useRecipe } from "~/composables/recipes";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import { useLoggedInState } from "~/composables/use-logged-in-state";

/*
 * "How was it?" told later, reached from Home: the end of cook mode on its own, for a meal cooked without it,
 * ticked done in the planner, or skipped at the end of cook mode. Query: `on` (the day cooked, YYYY-MM-DD),
 * `entry` (the meal plan entry) and `scale`.
 */
definePageMeta({ middleware: ["auth"] });

const i18n = useI18n();
const route = useRoute();
const auth = useMealieAuth();
const { isOwnGroup } = useLoggedInState();
const slug = route.params.slug as string;
const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");
const homeTo = computed(() => `/g/${groupSlug.value}`);
const recipeTo = computed(() => `/g/${groupSlug.value}/r/${slug}`);

const today = format(new Date(), "yyyy-MM-dd");
const queryOn = String(route.query.on ?? "");
// A day in the future cannot have been cooked yet; the server refuses it too.
const cookedOn = /^\d{4}-\d{2}-\d{2}$/.test(queryOn) && queryOn <= today ? queryOn : today;
const queryEntry = Number.parseInt(String(route.query.entry ?? ""), 10);
const entryId = queryEntry > 0 ? queryEntry : undefined;
const queryScale = Number.parseFloat(String(route.query.scale ?? ""));
const scale = queryScale > 0 && Number.isFinite(queryScale) ? queryScale : 1;

const dayLabel = computed(() => {
  const days = differenceInCalendarDays(parseISO(today), parseISO(cookedOn));
  if (days === 0) {
    return i18n.t("cook.cooked-today");
  }
  if (days === 1) {
    return i18n.t("cook.cooked-yesterday");
  }
  const date = parseISO(cookedOn).toLocaleDateString(i18n.locale.value, { weekday: "long", day: "numeric", month: "long" });
  return i18n.t("cook.cooked-on", { date: date.replace(/,/g, "") });
});

// Cooking is recorded for the household: anyone else just gets the recipe.
if (!isOwnGroup.value) {
  navigateTo(recipeTo.value, { replace: true });
}

const { recipe, loading } = useRecipe(slug);
const notFound = ref(false);
watch(loading, (now, before) => {
  notFound.value = before && !now && !recipe.value;
});

const { recipeImage } = useStaticRoutes();
const imageFailed = ref(false);
const imageUrl = computed(() => (recipe.value?.id && recipe.value.image ? recipeImage(recipe.value.id, recipe.value.image) : ""));

useAppShellTitle(() => i18n.t("cook.how-was-it"));
useSeoMeta({ title: () => recipe.value?.name || i18n.t("cook.how-was-it") });
</script>

<style scoped>
.finish-page {
  max-width: 640px;
}

.finish-page__status {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: calc(var(--ds-space) * 1.5);
  margin: 0;
}

.finish-page__link {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.finish-page__recipe {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  margin-bottom: calc(var(--ds-space) * 3);
  color: inherit;
  text-decoration: none;
}

.finish-page__photo {
  display: grid;
  flex: none;
  place-items: center;
  width: calc(var(--ds-space) * 8);
  height: calc(var(--ds-space) * 8);
  overflow: hidden;
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text-2);
}

.finish-page__photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.finish-page__text {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.25);
}

.finish-page__name {
  overflow-wrap: anywhere;
  font-size: var(--ds-t-4);
  font-weight: 700;
  line-height: 1.2;
}

.finish-page__day {
  font-size: var(--ds-t-2);
}

/* On its own page the screen needs no rule above it, and the shell's title already asks the question. */
.finish-page__finish {
  padding-top: 0;
  border-top: 0;
}

.finish-page__finish :deep(.cook-finish__title) {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
