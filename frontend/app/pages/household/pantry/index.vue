<template>
  <div class="pantry-page">
    <!-- Polite announcements: loading, then nothing once the pantry is on screen. -->
    <p class="pantry-page__sr" role="status">
      {{ loading && !items.length ? $t("pantry.loading") : "" }}
    </p>
    <p v-if="failed" class="pantry-page__hint" role="alert">
      <span class="pantry-page__hint-title">{{ $t("pantry.load-failed") }}</span>
      <button type="button" class="pantry-page__retry ds-focus" @click="refresh">
        {{ $t("pantry.try-again") }}
      </button>
    </p>

    <div class="pantry-page__body">
      <p v-if="items.length" class="pantry-page__summary">
        <strong>{{ $t("pantry.item-count", { count: items.length }, items.length) }}</strong>
        <template v-if="counts.past">
          · {{ $t("pantry.summary-past", { count: counts.past }, counts.past) }}
        </template>
        <template v-if="counts.check">
          · {{ $t("pantry.summary-check", { count: counts.check }, counts.check) }}
        </template>
      </p>

      <!-- First in the DOM after the summary (it is the main action); CSS pins it at the bottom on mobile. -->
      <PantryQuickAdd ref="quickAdd" class="pantry-page__add" @add="add" />

      <div v-if="empty" class="pantry-page__empty">
        <p class="pantry-page__empty-title">
          {{ $t("pantry.empty-title") }}
        </p>
        <p class="pantry-page__empty-text ds-muted">
          {{ $t("pantry.empty-text") }}
        </p>
        <div class="pantry-page__empty-actions">
          <DsButton variant="dark" :to="lastShopPath">
            {{ $t("pantry.put-away-last-shop") }}
          </DsButton>
          <DsButton variant="line" @click="focusQuickAdd">
            {{ $t("pantry.add-an-item") }}
          </DsButton>
        </div>
      </div>

      <template v-else-if="items.length">
        <div class="pantry-page__tools">
          <label class="pantry-page__search">
            <span class="pantry-page__sr">{{ $t("pantry.search") }}</span>
            <DsIcon name="search" :size="18" class="pantry-page__search-icon" />
            <input
              v-model="query"
              type="search"
              class="pantry-page__search-input"
              :placeholder="$t('pantry.search')"
              autocomplete="off"
              enterkeyhint="search"
            >
          </label>
          <div class="pantry-page__chips" role="group" :aria-label="$t('pantry.filters')">
            <button
              v-for="chip in chips"
              :key="chip.key"
              type="button"
              class="pantry-page__chip ds-focus"
              :class="{ 'pantry-page__chip--check': chip.key === 'check' }"
              :aria-pressed="filter === chip.key"
              @click="filter = chip.key"
            >
              {{ chip.label }}
              <span class="pantry-page__chip-count">{{ chip.count }}</span>
            </button>
          </div>
        </div>

        <PantryUseFirst
          v-if="showUseFirst"
          :items="items"
          :today="today"
          @edit="openEditor"
          @remove="removeItem"
        />

        <div v-if="visibleGroups.length" class="pantry-page__places">
          <div v-if="filter === 'all' && !query" class="pantry-page__section">
            <h2 class="pantry-page__section-title">
              {{ $t("pantry.by-place") }}
            </h2>
            <span class="pantry-page__section-hint">{{ $t("pantry.hold-to-move") }}</span>
          </div>
          <PantryList
            :by-location="visibleGroups"
            :today="today"
            :foldable="filter === 'all' && !query"
            @edit="openEditor"
            @opened="item => markOpened(item.id)"
            @remove="removeItem"
            @move="moveItem"
          />
        </div>
        <p v-else class="pantry-page__none ds-muted">
          {{ query ? $t("pantry.no-match", { query }) : $t("pantry.nothing-to-check") }}
        </p>
      </template>
    </div>

    <PantryItemDialog
      v-model="editor.open"
      :item="editor.item"
      :units="allUnits || []"
      :save-item="update"
    />
  </div>
</template>

<script setup lang="ts">
import { nextTick, useTemplateRef } from "vue";
import DsButton from "~/components/Design/DsButton.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import PantryItemDialog from "~/components/Domain/Pantry/PantryItemDialog.vue";
import PantryList from "~/components/Domain/Pantry/PantryList.vue";
import PantryQuickAdd from "~/components/Domain/Pantry/PantryQuickAdd.vue";
import PantryUseFirst from "~/components/Domain/Pantry/PantryUseFirst.vue";
import { useUserApi } from "~/composables/api";
import { useUnitStore } from "~/composables/store";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import { useDayRollover } from "~/composables/use-day-rollover";
import { usePantry } from "~/composables/use-pantry";
import { alert } from "~/composables/use-toast";
import { freshnessOf, groupByLocation, NEEDS_ATTENTION } from "~/lib/pantry/freshness";
import type { PantryItemOut, PantryLocation } from "~/lib/api/types/household";

definePageMeta({
  middleware: ["auth"],
});

const i18n = useI18n();
const route = useRoute();
const router = useRouter();
const api = useUserApi();

useAppShellTitle(() => i18n.t("pantry.title"));
useSeoMeta({ title: () => i18n.t("pantry.title") });

const today = useDayRollover();
const { store: allUnits } = useUnitStore();
const { items, byLocation, loading, failed, refresh, add, restore, update, remove, markOpened } = usePantry();

const empty = computed(() => !loading.value && !failed.value && !items.value.length);

// =====================================================
// Freshness, search and filters

const statuses = computed(() => new Map(items.value.map(item => [item.id, freshnessOf(item, today.value).status])));
const needsAttention = (item: PantryItemOut) => NEEDS_ATTENTION.includes(statuses.value.get(item.id) ?? "unknown");

/** The summary line: probably past, and the rest of what needs a look (worth checking or use soon). */
const counts = computed(() => {
  const all = [...statuses.value.values()];
  return {
    past: all.filter(status => status === "past").length,
    check: all.filter(status => status === "check" || status === "soon").length,
  };
});

type Filter = "all" | "check" | PantryLocation;
const filter = ref<Filter>("all");
const query = ref("");

/** Lower case, no accents: "gruyere" finds "Gruyère". */
function plain(text: string) {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase();
}

const searched = computed(() => {
  const wanted = plain(query.value.trim());
  if (!wanted) {
    return items.value;
  }
  return items.value.filter(item => plain(`${item.name} ${item.food?.name ?? ""}`).includes(wanted));
});

const chips = computed(() => {
  const attention = items.value.filter(needsAttention).length;
  return [
    { key: "all" as Filter, label: i18n.t("pantry.filter-all"), count: items.value.length },
    ...(attention ? [{ key: "check" as Filter, label: i18n.t("pantry.filter-check"), count: attention }] : []),
    ...byLocation.value.map(group => ({
      key: group.location as Filter,
      label: i18n.t(`pantry.location.${group.location}`),
      count: group.items.length,
    })),
  ];
});

// A filter whose chip went away (its last item moved or removed) falls back to everything.
watch(chips, (list) => {
  if (!list.some(chip => chip.key === filter.value)) {
    filter.value = "all";
  }
});

const visibleGroups = computed(() => {
  const shown = searched.value.filter(item =>
    filter.value === "all"
    || (filter.value === "check" ? needsAttention(item) : (item.location ?? "cupboard") === filter.value));
  return groupByLocation(shown);
});

const showUseFirst = computed(() => filter.value === "all" && !query.value.trim() && items.value.some(needsAttention));

// =====================================================
// Quick add: "?add=1" (the "+" menu's "Add to pantry") lands in the field, also when already on the page.

const quickAdd = useTemplateRef<InstanceType<typeof PantryQuickAdd>>("quickAdd");

function focusQuickAdd() {
  quickAdd.value?.focus();
}

watch(
  () => route.query.add,
  async (value) => {
    if (!value) {
      return;
    }
    await nextTick();
    focusQuickAdd();
    // Drop the flag so choosing "Add to pantry" again focuses the field again.
    router.replace({ query: { ...route.query, add: undefined } });
  },
  { immediate: true },
);

// =====================================================
// Empty state: "Put away your last shop" opens the most recently updated list, else the lists page.

const lastListId = ref<string | null>(null);
const lastShopPath = computed(() => (lastListId.value ? `/shopping-lists/${lastListId.value}` : "/shopping-lists"));

watch(empty, async (isEmpty) => {
  if (!isEmpty || lastListId.value) {
    return;
  }
  const { data } = await api.shopping.lists.getAll(1, 1, { orderBy: "updated_at", orderDirection: "desc" });
  lastListId.value = data?.items?.[0]?.id ?? null;
}, { immediate: true });

// =====================================================
// Editing and removing

const editor = reactive({ open: false, item: null as PantryItemOut | null });

function openEditor(item: PantryItemOut) {
  editor.item = item;
  editor.open = true;
}

/** A drag onto another place: saved at once; on failure the reload puts the item back where it is stored. */
function moveItem(itemId: string, location: PantryLocation) {
  const current = items.value.find(item => item.id === itemId);
  if (current && current.location !== location) {
    update(itemId, { location });
  }
}

async function removeItem(item: PantryItemOut) {
  if (!(await remove(item.id))) {
    return;
  }
  // One-shot: a second press (or a double-click) must not put the item back twice.
  let undone = false;
  alert.info(i18n.t("pantry.removed", { name: item.name }), undefined, {
    timeout: 4000,
    action: {
      message: i18n.t("general.undo"),
      onClick: () => {
        if (undone) {
          return;
        }
        undone = true;
        restore(item);
      },
    },
  });
}
</script>

<style scoped>
.pantry-page {
  max-width: 1120px;
}

.pantry-page__body {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
}

.pantry-page__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.pantry-page__summary {
  margin: 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
}

.pantry-page__summary strong {
  color: var(--ds-text);
  font-weight: 650;
}

.pantry-page__tools {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 1.25);
}

.pantry-page__search {
  display: flex;
  align-items: center;
  gap: var(--ds-space);
  min-height: 46px;
  padding: 0 calc(var(--ds-space) * 1.5);
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.pantry-page__search:focus-within {
  border-color: var(--ds-text);
  outline: 2px solid var(--ds-text);
  outline-offset: 2px;
}

.pantry-page__search-icon {
  color: var(--ds-text-2);
}

.pantry-page__search-input {
  flex: 1;
  min-width: 0;
  min-height: 44px;
  padding: 0;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-3);
}

.pantry-page__search-input::placeholder {
  color: var(--ds-text-2);
}

/* Phone: one sideways-scrolling row of chips. */
.pantry-page__chips {
  display: flex;
  gap: calc(var(--ds-space) * 0.75);
  margin: 0 calc(var(--ds-space) * -2);
  padding: 0 calc(var(--ds-space) * 2) 2px;
  overflow-x: auto;
  scrollbar-width: none;
}

.pantry-page__chip {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: calc(var(--ds-space) * 0.75);
  min-height: 36px;
  padding: 0 calc(var(--ds-space) * 1.5);
  border: 1px solid var(--ds-border);
  border-radius: 999px;
  background: var(--ds-surface);
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-2);
  font-weight: 550;
  cursor: pointer;
}

.pantry-page__chip--check {
  border-color: var(--ds-soon-bar);
}

.pantry-page__chip[aria-pressed="true"] {
  border-color: var(--ds-text);
  background: var(--ds-text);
  color: var(--ds-surface);
}

.pantry-page__chip-count {
  color: var(--ds-text-2);
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.pantry-page__chip[aria-pressed="true"] .pantry-page__chip-count {
  color: inherit;
  opacity: 0.75;
}

.pantry-page__places {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 1.25);
}

.pantry-page__section {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--ds-space);
  margin: var(--ds-space) 2px 0;
}

.pantry-page__section-title {
  margin: 0;
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.01em;
}

.pantry-page__section-hint {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
}

.pantry-page__none {
  margin: 0;
  padding: calc(var(--ds-space) * 3) calc(var(--ds-space) * 2);
  border: 1px dashed var(--ds-border);
  border-radius: var(--ds-radius-card);
  font-size: var(--ds-t-2);
  text-align: center;
}

@media (min-width: 1024px) {
  .pantry-page__chips {
    flex-wrap: wrap;
    margin: 0;
    padding: 0;
    overflow: visible;
  }
}

.pantry-page__hint {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--ds-space);
  margin: 0 0 calc(var(--ds-space) * 2);
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
}

.pantry-page__hint-title {
  color: var(--ds-text);
  font-weight: 600;
}

.pantry-page__retry {
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text);
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.pantry-page__empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--ds-space);
  padding: calc(var(--ds-space) * 3);
  border: 1px dashed var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.pantry-page__empty-title {
  margin: 0;
  font-size: var(--ds-t-3);
  font-weight: 600;
}

.pantry-page__empty-text {
  margin: 0;
  max-width: 70ch;
  font-size: var(--ds-t-2);
}

.pantry-page__empty-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
  margin-top: var(--ds-space);
}

/* Mobile: the field rides just above the floating tab bar while the list scrolls under it. */
@media (max-width: 1023px) {
  .pantry-page__add {
    position: sticky;
    bottom: var(--ds-tabbar-clearance, calc(var(--ds-space) * 2));
    z-index: 2;
    order: 99;
    box-shadow: var(--ds-shadow-float);
  }
}
</style>
