<template>
  <section v-if="rows.length" class="read-nutrition" :aria-labelledby="headingId">
    <h2 :id="headingId" class="read-nutrition__heading">
      <button
        type="button"
        class="read-nutrition__toggle ds-focus"
        :aria-expanded="open ? 'true' : 'false'"
        :aria-controls="listId"
        @click="open = !open"
      >
        {{ $t("recipe-read.nutrition") }}
        <DsIcon name="chevronDown" :size="22" class="read-nutrition__chevron" :class="{ 'read-nutrition__chevron--open': open }" />
      </button>
    </h2>
    <dl v-show="open" :id="listId" class="read-nutrition__list">
      <div v-for="row in rows" :key="row.key" class="read-nutrition__row">
        <dt>{{ row.label }}</dt>
        <dd>{{ row.value }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { useNutritionLabels } from "~/composables/recipes";
import type { Nutrition } from "~/lib/api/types/recipe";

const props = defineProps<{ nutrition: Nutrition | null | undefined }>();

const headingId = useId();
const listId = useId();
// Starts collapsed: it is reference, not reading.
const open = ref(false);

const { labels } = useNutritionLabels();

// Same mapping as upstream RecipeNutrition: only the values that are filled in, with their unit.
const rows = computed(() =>
  Object.entries(labels).flatMap(([key, label]) => {
    const value = props.nutrition?.[key as keyof Nutrition]?.trim();
    return value ? [{ key, label: label.label, value: label.suffix ? `${value} ${label.suffix}` : value }] : [];
  }),
);
</script>

<style scoped>
.read-nutrition__heading {
  margin: 0;
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

.read-nutrition__toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: calc(var(--ds-space) * 5.5);
  padding: 0;
  border: 0;
  border-bottom: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl) var(--ds-radius-ctl) 0 0;
  background: none;
  color: inherit;
  font: inherit;
  letter-spacing: inherit;
  text-align: left;
  cursor: pointer;
}

.read-nutrition__chevron {
  transition: transform 160ms ease;
}

.read-nutrition__chevron--open {
  transform: rotate(180deg);
}

.read-nutrition__list {
  margin: 0;
  max-width: 70ch;
}

.read-nutrition__row {
  display: flex;
  justify-content: space-between;
  gap: calc(var(--ds-space) * 2);
  padding: var(--ds-space) 0;
  border-bottom: 1px solid var(--ds-border);
  font-size: var(--ds-t-3);
}

.read-nutrition__row dt {
  color: var(--ds-text-2);
}

.read-nutrition__row dd {
  margin: 0;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

@media (prefers-reduced-motion: reduce) {
  .read-nutrition__chevron {
    transition: none;
  }
}
</style>
