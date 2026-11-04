<template>
  <section class="pantry-use-first" :aria-labelledby="headingId">
    <div class="pantry-use-first__head">
      <h2 :id="headingId" class="pantry-use-first__title">
        <span class="pantry-use-first__mark" aria-hidden="true" />
        {{ $t("pantry.use-first") }}
      </h2>
      <span class="pantry-use-first__note" :title="$t('pantry.estimate-hint')">{{ $t("pantry.estimate") }}</span>
    </div>
    <ul class="pantry-use-first__cards" role="list">
      <li
        v-for="{ item, freshness } in entries"
        :key="item.id"
        class="pantry-use-first__card"
        :class="`pantry-use-first__card--${freshness.status}`"
      >
        <span class="pantry-use-first__tag">{{ $t(`pantry.status.${freshness.status}`) }}</span>
        <span class="pantry-use-first__name">{{ item.name }}</span>
        <span class="pantry-use-first__meta">{{ meta(item, freshness) }}</span>
        <span class="pantry-use-first__actions">
          <DsButton variant="line" @click="$emit('remove', item)">
            {{ $t("pantry.throw-away") }}
          </DsButton>
          <DsButton variant="line" @click="$emit('edit', item)">
            {{ $t("pantry.edit") }}
          </DsButton>
        </span>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import DsButton from "~/components/Design/DsButton.vue";
import { freshnessLine, freshnessOf, FRESHNESS_RANK, NEEDS_ATTENTION, type Freshness } from "~/lib/pantry/freshness";
import type { PantryItemOut } from "~/lib/api/types/household";

const props = defineProps<{
  items: PantryItemOut[];
  today: Date;
}>();

defineEmits<{
  (e: "edit" | "remove", item: PantryItemOut): void;
}>();

const i18n = useI18n();
const headingId = useId();

/** Every item that needs attention, worst first, then soonest. */
const entries = computed(() =>
  props.items
    .map(item => ({ item, freshness: freshnessOf(item, props.today) }))
    .filter(({ freshness }) => NEEDS_ATTENTION.includes(freshness.status))
    .sort((a, b) =>
      FRESHNESS_RANK[a.freshness.status] - FRESHNESS_RANK[b.freshness.status]
      || (a.freshness.daysLeft ?? 0) - (b.freshness.daysLeft ?? 0)),
);

/** "Opened 8 days ago · keeps about 7 days": the date, plus the keeping time when it is an estimate. */
function meta(item: PantryItemOut, freshness: Freshness) {
  const date = freshnessLine(item, props.today, (key, params) => i18n.t(key, params ?? {}), i18n.locale.value)?.text ?? "";
  if (!freshness.estimated || freshness.keepsDays === null) {
    return date;
  }
  return `${date} · ${i18n.t("pantry.keeps-days", { days: freshness.keepsDays }, freshness.keepsDays)}`;
}
</script>

<style scoped>
.pantry-use-first__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--ds-space);
  margin: 0 2px calc(var(--ds-space) * 1.25);
}

.pantry-use-first__title {
  display: flex;
  align-items: center;
  gap: var(--ds-space);
  margin: 0;
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.01em;
}

/* The screen's one touch of saffron. */
.pantry-use-first__mark {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--ds-accent);
}

.pantry-use-first__note {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  cursor: help;
}

/* Phone: a row of cards that scrolls sideways, bleeding to the screen edge. */
.pantry-use-first__cards {
  display: flex;
  gap: calc(var(--ds-space) * 1.25);
  margin: 0 calc(var(--ds-space) * -2);
  padding: 0 calc(var(--ds-space) * 2) 4px;
  overflow-x: auto;
  list-style: none;
  scroll-snap-type: x proximity;
  scrollbar-width: none;
}

.pantry-use-first__card {
  position: relative;
  display: flex;
  flex: none;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.75);
  width: 184px;
  padding: calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 2);
  overflow: hidden;
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  scroll-snap-align: start;
}

/* A status bar down the left edge: amber to check or use soon, red when probably past. */
.pantry-use-first__card::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: var(--ds-soon-bar);
  content: "";
}

.pantry-use-first__card--past::before {
  background: var(--ds-missing);
}

.pantry-use-first__tag {
  align-self: flex-start;
  padding: 2px calc(var(--ds-space) * 1);
  border-radius: 999px;
  background: var(--ds-soon-surface);
  color: var(--ds-soon);
  font-size: var(--ds-t-1);
  font-weight: 600;
}

.pantry-use-first__card--past .pantry-use-first__tag {
  background: var(--ds-missing-surface);
  color: var(--ds-missing);
}

.pantry-use-first__name {
  font-size: var(--ds-t-3);
  font-weight: 650;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.pantry-use-first__meta {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  line-height: 1.3;
}

.pantry-use-first__actions {
  display: flex;
  gap: calc(var(--ds-space) * 0.75);
  margin-top: auto;
  padding-top: calc(var(--ds-space) * 0.5);
}

.pantry-use-first__actions > * {
  flex: 1;
  min-width: 0;
}

/* Desktop: a grid instead of a sideways row. */
@media (min-width: 1024px) {
  .pantry-use-first__cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    margin: 0;
    padding: 0;
    overflow: visible;
  }

  .pantry-use-first__card {
    width: auto;
  }
}
</style>
