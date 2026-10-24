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
      <!-- First in the DOM (it is the main action); CSS pins it at the bottom on mobile. -->
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

      <PantryList
        v-else
        :by-location="byLocation"
        :today="today"
        @edit="openEditor"
        @opened="item => markOpened(item.id)"
        @remove="removeItem"
      />
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
import PantryItemDialog from "~/components/Domain/Pantry/PantryItemDialog.vue";
import PantryList from "~/components/Domain/Pantry/PantryList.vue";
import PantryQuickAdd from "~/components/Domain/Pantry/PantryQuickAdd.vue";
import { useUserApi } from "~/composables/api";
import { useUnitStore } from "~/composables/store";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import { useDayRollover } from "~/composables/use-day-rollover";
import { usePantry } from "~/composables/use-pantry";
import { alert } from "~/composables/use-toast";
import type { PantryItemOut } from "~/lib/api/types/household";

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
  max-width: 760px;
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
