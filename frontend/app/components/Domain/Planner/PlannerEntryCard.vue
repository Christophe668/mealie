<template>
  <article
    class="planner-card"
    :class="[`planner-card--${layout}`, { 'planner-card--note': !recipe, 'planner-card--done': isCooked }]"
    :data-entry-id="entry.id"
  >
    <span v-if="recipe" class="planner-card__media">
      <img
        v-if="imageUrl && !imageFailed"
        :src="imageUrl"
        alt=""
        loading="lazy"
        draggable="false"
        @error="imageFailed = true"
      >
      <DsIcon v-else name="silverwareForkKnife" :size="20" class="planner-card__placeholder" />
    </span>

    <div class="planner-card__body">
      <NuxtLink
        v-if="recipeTo"
        :to="recipeTo"
        class="planner-card__title planner-card__link ds-focus"
        draggable="false"
      >
        {{ title }}
      </NuxtLink>
      <button
        v-else
        type="button"
        class="planner-card__title planner-card__link ds-focus"
        @click="emit('edit', entry)"
      >
        {{ title }}
      </button>
      <span v-if="servingsLabel" class="planner-card__fact">{{ servingsLabel }}</span>
      <button
        type="button"
        class="planner-card__cooked ds-focus"
        :aria-pressed="isCooked"
        :disabled="busy"
        @click="toggleCooked"
      >
        <DsIcon :name="isCooked ? 'checkBold' : 'check'" :size="16" />
        {{ $t("planner.cooked") }}
      </button>
    </div>

    <!-- Capture: the trigger's own click opens the menu, so the menu is back on its first step by then. -->
    <AppShellMenu
      ref="menu"
      class="planner-card__menu"
      :items="menuItems"
      :label="menuLabel"
      :trigger-label="$t('planner.entry-actions', { title })"
      trigger-class="planner-card__kebab ds-focus"
      :placement="menuPlacement"
      @click.capture="onMenuClick"
    >
      <template #trigger>
        <DsIcon name="dotsVertical" :size="20" />
      </template>
    </AppShellMenu>
  </article>
</template>

<script setup lang="ts">
import { format } from "date-fns";
import { nextTick, useTemplateRef } from "vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import AppShellMenu from "~/components/Layout/AppShellMenu.vue";
import { useStaticRoutes, useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import { apiErrorInfo } from "~/lib/api/error-info";
import type { PlanEntryType, ReadPlanEntry } from "~/lib/api/types/meal-plan";
import type { AppShellMenuItem } from "~/types/application-types";

export interface PlannerMoveTarget {
  /** yyyy-MM-dd */
  date: string;
  label: string;
}

export interface PlannerMove {
  entryId: number;
  /** yyyy-MM-dd */
  date: string;
  entryType: PlanEntryType;
}

const props = withDefaults(defineProps<{
  entry: ReadPlanEntry;
  groupSlug: string;
  /** stack = photo strip above the title (week grid), row = square thumb beside it (day list). */
  layout?: "stack" | "row";
  /** Days the "Move to…" step offers; the entry's own day is left out. */
  moveTargets?: PlannerMoveTarget[];
  menuPlacement?: "bottom-start" | "bottom-end";
}>(), {
  layout: "stack",
  moveTargets: () => [],
  menuPlacement: "bottom-end",
});

const emit = defineEmits<{
  remove: [entryId: number];
  edit: [entry: ReadPlanEntry];
  move: [move: PlannerMove];
}>();

const i18n = useI18n();
const { recipeSmallImage } = useStaticRoutes();
const menu = useTemplateRef<InstanceType<typeof AppShellMenu>>("menu");

const recipe = computed(() => props.entry.recipe ?? null);
const title = computed(() => recipe.value?.name || props.entry.title || "");
const recipeTo = computed(() => (recipe.value?.slug ? `/g/${props.groupSlug}/r/${recipe.value.slug}` : ""));

const imageFailed = ref(false);
const imageUrl = computed(() =>
  recipe.value?.id && recipe.value.image ? recipeSmallImage(recipe.value.id, recipe.value.image) : "",
);
watch(imageUrl, () => (imageFailed.value = false));

/** Servings only when the plan asks for a different amount than the recipe makes. */
const servingsLabel = computed(() => {
  const scale = props.entry.recipeScale ?? 1;
  if (!recipe.value || scale === 1) {
    return "";
  }
  const base = recipe.value.recipeServings || recipe.value.recipeYieldQuantity || 0;
  if (base > 0) {
    return i18n.t("planner.for-servings", { servings: i18n.n(base * scale, { maximumFractionDigits: 1 }) });
  }
  return i18n.t("planner.scaled", { scale: i18n.n(scale, { maximumFractionDigits: 2 }) });
});

const cookedAt = ref(props.entry.cookedAt ?? null);
watch(() => props.entry.cookedAt, value => (cookedAt.value = value ?? null));
const isCooked = computed(() => !!cookedAt.value);
const busy = ref(false);

/** Ticks the meal done on the cook's own local day, or takes the tick back. */
async function toggleCooked() {
  if (busy.value) {
    return;
  }
  busy.value = true;
  const api = useUserApi().householdCooking;
  try {
    if (isCooked.value) {
      const { error } = await api.unmarkCooked(props.entry.id);
      if (error) {
        throw error;
      }
      cookedAt.value = null;
    }
    else {
      // The entry's own day, but never a day still to come.
      const today = format(new Date(), "yyyy-MM-dd");
      const result = await api.markCooked(props.entry.id, props.entry.date <= today ? props.entry.date : today);
      if (result.error) {
        // 409: this meal (or a cooking of the recipe that day) is recorded already; the card stays as it is
        alert.error(apiErrorInfo(result).message ?? i18n.t("planner.cooked-failed"));
        return;
      }
      cookedAt.value = result.data?.mealPlanEntry?.cookedAt ?? new Date().toISOString();
    }
  }
  catch {
    alert.error(i18n.t("planner.cooked-failed"));
  }
  finally {
    busy.value = false;
  }
}

const step = ref<"actions" | "move">("actions");

const menuLabel = computed(() =>
  step.value === "move" ? i18n.t("planner.move-to-label", { title: title.value }) : i18n.t("planner.entry-actions", { title: title.value }),
);

async function showMoveStep() {
  step.value = "move";
  await nextTick();
  menu.value?.open();
}

const menuItems = computed<AppShellMenuItem[]>(() => {
  if (step.value === "move") {
    return props.moveTargets
      .filter(target => target.date !== props.entry.date)
      .map(target => ({
        key: target.date,
        label: target.label,
        icon: "calendar",
        onSelect: () => {
          step.value = "actions";
          emit("move", { entryId: props.entry.id, date: target.date, entryType: props.entry.entryType ?? "dinner" });
        },
      }));
  }

  const items: AppShellMenuItem[] = [];
  if (recipeTo.value) {
    items.push(
      { key: "open", label: i18n.t("planner.open-recipe"), icon: "silverwareForkKnife", to: recipeTo.value },
      { key: "servings", label: i18n.t("planner.change-servings"), icon: "edit", onSelect: () => emit("edit", props.entry) },
    );
  }
  else {
    items.push({ key: "edit", label: i18n.t("planner.edit"), icon: "edit", onSelect: () => emit("edit", props.entry) });
  }
  if (props.moveTargets.length) {
    items.push({ key: "move", label: i18n.t("planner.move-to"), icon: "calendar", onSelect: showMoveStep });
  }
  items.push({
    key: "remove",
    label: i18n.t("planner.remove"),
    icon: "calendarRemove",
    dividerBefore: true,
    onSelect: () => emit("remove", props.entry.id),
  });
  return items;
});

function onMenuClick(event: MouseEvent) {
  if ((event.target as Element | null)?.closest("[aria-haspopup=menu]")) {
    step.value = "actions";
  }
}
</script>

<style scoped>
.planner-card {
  position: relative;
  display: grid;
  min-width: 0;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  background: var(--ds-surface);
  color: var(--ds-text);
}

.planner-card--stack {
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-rows: auto 1fr;
}

.planner-card--row {
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
}

.planner-card--row.planner-card--note {
  grid-template-columns: minmax(0, 1fr) auto;
}

.planner-card__media {
  display: grid;
  place-items: center;
  overflow: hidden;
  background: var(--ds-bg);
  color: var(--ds-text-2);
}

.planner-card--stack .planner-card__media {
  grid-column: 1 / -1;
  height: 56px;
  border-radius: calc(var(--ds-radius-card) - 1px) calc(var(--ds-radius-card) - 1px) 0 0;
}

.planner-card--row .planner-card__media {
  width: 56px;
  height: 56px;
  margin: var(--ds-space);
  margin-right: 0;
  border-radius: calc(var(--ds-radius-card) - 4px);
}

.planner-card__media img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.planner-card__placeholder {
  opacity: 0.6;
}

.planner-card__body {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.5);
  padding: var(--ds-space) 0 var(--ds-space) calc(var(--ds-space) * 1.25);
}

.planner-card--row .planner-card__body {
  padding-left: calc(var(--ds-space) * 1.5);
}

.planner-card__title {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  color: var(--ds-text);
  font-size: var(--ds-t-2);
  font-weight: 500;
  line-height: 1.25;
  overflow-wrap: break-word;
  hyphens: auto;
  text-align: left;
  text-decoration: none;
}

.planner-card__link {
  padding: 0;
  border: 0;
  border-radius: 2px;
  background: none;
  font-family: inherit;
  cursor: pointer;
}

.planner-card__link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.planner-card__fact {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
}

.planner-card__cooked {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: calc(var(--ds-space) * 0.5);
  min-height: 32px;
  padding: 0 calc(var(--ds-space) * 0.75) 0 calc(var(--ds-space) * 0.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text-2);
  font-family: inherit;
  font-size: var(--ds-t-1);
  line-height: 1.75;
  cursor: pointer;
}

.planner-card__cooked[aria-pressed="true"] {
  border-color: var(--ds-accent);
  background: var(--ds-accent);
  color: var(--ds-accent-text);
}

.planner-card__cooked:disabled {
  cursor: progress;
}

.planner-card--done .planner-card__media {
  opacity: 0.6;
}

.planner-card__menu {
  align-self: start;
}

.planner-card__menu :deep(.planner-card__kebab) {
  display: grid;
  place-items: center;
  width: calc(var(--ds-space) * 4);
  height: calc(var(--ds-space) * 4);
  margin: calc(var(--ds-space) * 0.5);
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text-2);
  cursor: pointer;
}

.planner-card__menu :deep(.planner-card__kebab:hover) {
  background: var(--ds-bg);
  color: var(--ds-text);
}

/* Above the neighbouring cards and their menus' triggers. */
.planner-card__menu :deep(.ds-menu__list) {
  z-index: 5;
}

.planner-card--row .planner-card__menu {
  align-self: center;
}

/* On a photo card the kebab sits on the photo, so the title gets the card's full width. */
.planner-card--stack:not(.planner-card--note) .planner-card__body {
  grid-column: 1 / -1;
  padding-right: calc(var(--ds-space) * 1.25);
}

.planner-card--stack:not(.planner-card--note) .planner-card__menu {
  position: absolute;
  top: 0;
  right: 0;
}

.planner-card--stack:not(.planner-card--note) .planner-card__menu :deep(.planner-card__kebab) {
  background: var(--ds-surface);
  color: var(--ds-text);
}
</style>
