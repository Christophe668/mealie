<template>
  <DsSheet v-model="open" :title="title" :busy="busy">
    <template #header>
      <header class="recipe-sheet__header">
        <h2 class="recipe-sheet__title">
          {{ title }}
        </h2>
        <template v-if="step === 'actions'">
          <span v-if="status" class="recipe-sheet__tag" :class="`recipe-sheet__tag--${status}`">
            <DsIcon :name="STATUS_ICON[status]" :size="14" />
            {{ $t(`recipe-read.status-${status}`) }}
          </span>
          <p class="recipe-sheet__detail">
            {{ detail }}
          </p>
        </template>
        <p v-else-if="ingredient" class="recipe-sheet__detail">
          {{ $t("recipe-ingredient-sheet.pick-list") }}
        </p>
      </header>
    </template>

    <!-- Which shopping list: shown before an add when the household has several. -->
    <div v-if="step === 'pick'" ref="picker" class="recipe-sheet__picker">
      <button
        v-for="list in orderedLists"
        :key="list.id"
        type="button"
        class="ds-sheet__action"
        :aria-current="list.id === lastListId ? 'true' : undefined"
        :disabled="busy"
        @click="chooseList(list.id)"
      >
        <DsIcon :name="list.id === lastListId ? 'check' : 'formatListCheck'" />
        <span class="recipe-sheet__label">{{ list.name }}</span>
      </button>
    </div>

    <template v-else-if="ingredient && !items.length">
      <button type="button" class="ds-sheet__action" :disabled="busy" @click="emit('i-have-it', location, useBy || undefined)">
        <DsIcon name="checkboxMarkedCircle" />
        <span>
          <span class="recipe-sheet__label">{{ $t("recipe-ingredient-sheet.i-have-it") }}</span>
          <span class="ds-sheet__hint">{{ $t("recipe-ingredient-sheet.i-have-it-hint") }}</span>
        </span>
      </button>
      <div class="recipe-sheet__places">
        <DsPlaceChips v-model="location" />
        <label v-if="showUseBy" class="recipe-sheet__use-by-field">
          <span class="recipe-sheet__use-by-label">{{ $t("recipe-ingredient-sheet.use-by-label") }}</span>
          <input ref="useByInput" v-model="useBy" type="date" class="recipe-sheet__date">
        </label>
        <button v-else type="button" class="recipe-sheet__use-by ds-focus" @click="revealUseBy">
          {{ $t("recipe-ingredient-sheet.add-use-by") }}
        </button>
      </div>
      <button v-if="lists.length" type="button" class="ds-sheet__action" :disabled="busy" @click="toList('add-to-list')">
        <DsIcon name="cartCheck" />
        <span>
          <span class="recipe-sheet__label">{{ $t("recipe-ingredient-sheet.add-to-list") }}</span>
          <span v-if="listHint" class="ds-sheet__hint">{{ listHint }}</span>
        </span>
      </button>
    </template>

    <template v-else-if="ingredient">
      <button v-if="lists.length" type="button" class="ds-sheet__action" :disabled="busy" @click="toList('running-low')">
        <DsIcon name="cartCheck" />
        <span>
          <span class="recipe-sheet__label">{{ $t("recipe-ingredient-sheet.running-low") }}</span>
          <span class="ds-sheet__hint">{{ listHint || $t("recipe-ingredient-sheet.running-low-hint") }}</span>
        </span>
      </button>
      <!-- One block per pantry row (fridge and freezer, say); its actions apply to that row only. -->
      <section v-for="row in rows" :key="row.item.id" class="recipe-sheet__row" :aria-label="row.place">
        <p v-if="rows.length > 1" class="recipe-sheet__row-title">
          {{ [row.place, row.fresh].filter(Boolean).join(" · ") }}
        </p>
        <button
          v-if="!row.openedToday"
          type="button"
          class="ds-sheet__action"
          :disabled="busy"
          @click="emit('opened-today', row.item)"
        >
          <DsIcon name="clockOutline" />
          <span class="recipe-sheet__label">{{ $t("recipe-ingredient-sheet.opened-today") }}</span>
        </button>
        <button type="button" class="ds-sheet__action" :disabled="busy" @click="emit('edit', row.item)">
          <DsIcon name="calendarEdit" />
          <span class="recipe-sheet__label">{{ $t("recipe-ingredient-sheet.edit") }}</span>
        </button>
        <button
          type="button"
          class="ds-sheet__action ds-sheet__action--danger"
          :disabled="busy"
          @click="emit('used-up', row.item)"
        >
          <DsIcon name="delete" />
          <span>
            <span class="recipe-sheet__label">{{ $t("recipe-ingredient-sheet.used-up") }}</span>
            <span class="ds-sheet__hint">{{ $t("recipe-ingredient-sheet.used-up-hint") }}</span>
          </span>
        </button>
      </section>
    </template>
  </DsSheet>
</template>

<script setup lang="ts">
import { format } from "date-fns";
import { nextTick, useTemplateRef } from "vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import DsPlaceChips from "~/components/Design/DsPlaceChips.vue";
import DsSheet from "~/components/Design/DsSheet.vue";
import type { PantryItemOut, PantryLocation, ShoppingListSummary } from "~/lib/api/types/household";
import type { RecipeIngredient } from "~/lib/api/types/recipe";
import { DEFAULT_PANTRY_LOCATION, freshnessLine } from "~/lib/pantry/freshness";
import { ingredientStatus, pantryDetail } from "~/lib/pantry/ingredient-status";

const props = defineProps<{
  /** The ingredient whose actions are shown; null makes the sheet the list picker for "Add N to list". */
  ingredient: RecipeIngredient | null;
  /** Its pantry rows; empty when it is missing. */
  items: PantryItemOut[];
  lists: ShoppingListSummary[];
  /** An action is saving: the buttons wait and the sheet stays open. */
  busy: boolean;
}>();

const emit = defineEmits<{
  "i-have-it": [location: PantryLocation, useBy: string | undefined];
  "add-to-list": [listId: string];
  "running-low": [listId: string];
  "add-missing": [listId: string];
  "opened-today": [item: PantryItemOut];
  "edit": [item: PantryItemOut];
  "used-up": [item: PantryItemOut];
}>();

const open = defineModel<boolean>({ default: false });

const STATUS_ICON = { have: "checkboxMarkedCircle", soon: "alertCircle", missing: "minusCircle" } as const;

const i18n = useI18n();

const foodName = computed(() => props.ingredient?.food?.name || props.ingredient?.note || "");
const title = computed(() => (props.ingredient ? foodName.value : i18n.t("recipe-ingredient-sheet.pick-list")));

const status = computed(() => (props.ingredient ? ingredientStatus(props.items, new Date()) : null));
const detail = computed(() =>
  props.items.length
    ? pantryDetail(props.items, new Date(), i18n.t, i18n.locale.value)
    : i18n.t("recipe-ingredient-sheet.not-in-pantry"),
);

const rows = computed(() => {
  const today = new Date();
  const todayText = format(today, "yyyy-MM-dd");
  return props.items.map(item => ({
    item,
    place: i18n.t(`pantry.location.${item.location ?? DEFAULT_PANTRY_LOCATION}`),
    fresh: freshnessLine(item, today, i18n.t, i18n.locale.value)?.text ?? "",
    openedToday: item.openedOn === todayText,
  }));
});

/* "I have it": the place, and a use-by only when asked for. */
const location = ref<PantryLocation>(DEFAULT_PANTRY_LOCATION);
const useBy = ref("");
const showUseBy = ref(false);
const useByInput = useTemplateRef<HTMLInputElement>("useByInput");

async function revealUseBy() {
  showUseBy.value = true;
  await nextTick();
  useByInput.value?.focus();
}

/* Which shopping list. */
type ListAction = "add-to-list" | "running-low" | "add-missing";
const step = ref<"actions" | "pick">("actions");
const pending = ref<ListAction>("add-to-list");
const lastListId = ref<string | null>(null);
const picker = useTemplateRef<HTMLElement>("picker");

function readLastList(): string | null {
  try {
    return sessionStorage.getItem(LAST_LIST_KEY);
  }
  catch {
    return null;
  }
}

const orderedLists = computed(() => {
  const last = props.lists.find(list => list.id === lastListId.value);
  return last ? [last, ...props.lists.filter(list => list !== last)] : props.lists;
});

/** "lemon → Weekly shop" when the add needs no choice. */
const listHint = computed(() =>
  props.lists.length === 1 && foodName.value
    ? i18n.t("recipe-ingredient-sheet.added-to-list", { item: foodName.value, list: props.lists[0]!.name })
    : "",
);

async function showPicker(action: ListAction) {
  pending.value = action;
  lastListId.value = readLastList();
  step.value = "pick";
  await nextTick();
  picker.value?.querySelector<HTMLElement>("button")?.focus();
}

function chooseList(listId: string) {
  try {
    sessionStorage.setItem(LAST_LIST_KEY, listId);
  }
  catch {
    // Private mode: the picker just won't remember.
  }
  lastListId.value = listId;
  // Typed per event so emit's overloads resolve.
  if (pending.value === "add-to-list") {
    emit("add-to-list", listId);
  }
  else if (pending.value === "running-low") {
    emit("running-low", listId);
  }
  else {
    emit("add-missing", listId);
  }
}

function toList(action: "add-to-list" | "running-low") {
  if (props.lists.length === 1) {
    pending.value = action;
    chooseList(props.lists[0]!.id);
    return;
  }
  showPicker(action);
}

// Each opening starts fresh: the actions (or the picker, for the missing ones), the default place, no use-by.
watch(
  () => [open.value, props.ingredient] as const,
  ([isOpen, ingredient]) => {
    if (!isOpen) {
      return;
    }
    location.value = DEFAULT_PANTRY_LOCATION;
    useBy.value = "";
    showUseBy.value = false;
    if (ingredient) {
      step.value = "actions";
    }
    else {
      showPicker("add-missing");
    }
  },
  { immediate: true },
);
</script>

<script lang="ts">
/** Session-storage key of the shopping list last added to from a recipe; the picker offers it first. */
export const LAST_LIST_KEY = "recipe-read:last-list";
</script>

<style scoped>
.recipe-sheet__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ds-space);
  margin-bottom: calc(var(--ds-space) * 1.5);
}

.recipe-sheet__title {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  font-size: var(--ds-t-4);
  font-weight: 700;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.recipe-sheet__tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px 4px 8px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
}

.recipe-sheet__tag--have {
  background: var(--ds-have-surface);
  color: var(--ds-have);
}

.recipe-sheet__tag--soon {
  background: var(--ds-soon-surface);
  color: var(--ds-soon);
}

.recipe-sheet__tag--missing {
  background: var(--ds-missing-surface);
  color: var(--ds-missing);
}

.recipe-sheet__detail {
  flex-basis: 100%;
  margin: 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
}

.recipe-sheet__label {
  display: block;
}

.recipe-sheet__places {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ds-space);
  padding: 0 0 calc(var(--ds-space) * 1.5);
}

.recipe-sheet__use-by {
  min-height: 40px;
  padding: 0 calc(var(--ds-space) * 1.5);
  border: 1px dashed var(--ds-border);
  border-radius: 999px;
  background: none;
  color: var(--ds-text-2);
  font: inherit;
  font-size: var(--ds-t-2);
  font-weight: 600;
  cursor: pointer;
}

.recipe-sheet__use-by-field {
  display: flex;
  align-items: center;
  gap: var(--ds-space);
  font-size: var(--ds-t-2);
}

.recipe-sheet__use-by-label {
  color: var(--ds-text-2);
}

.recipe-sheet__date {
  min-height: 40px;
  padding: 0 var(--ds-space);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  font: inherit;
}

.recipe-sheet__row-title {
  margin: calc(var(--ds-space) * 1.5) 0 calc(var(--ds-space) * 0.5);
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
</style>
