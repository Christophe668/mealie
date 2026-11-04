<template>
  <li class="pantry-row" :data-item-id="item.id">
    <!-- The whole row opens the editor; the kebab holds the quick actions. -->
    <button type="button" class="pantry-row__main ds-focus" @click="$emit('edit', item)">
      <span class="pantry-row__dot" :class="`pantry-row__dot--${freshness.status}`" aria-hidden="true" />
      <span class="pantry-row__text">
        <span class="pantry-row__name">{{ item.name }}</span>
        <span class="pantry-row__fresh" :class="`pantry-row__fresh--${freshness.status}`">
          {{ meta }}
        </span>
      </span>
      <span v-if="qty" class="pantry-row__qty">{{ qty }}</span>
    </button>
    <AppShellMenu
      class="pantry-row__menu"
      :items="actions"
      :label="$t('pantry.actions-for', { name: item.name })"
      :trigger-label="$t('pantry.actions-for', { name: item.name })"
      trigger-class="pantry-row__more ds-focus"
      placement="bottom-end"
    >
      <template #trigger>
        <DsIcon name="dotsVertical" :size="20" />
      </template>
    </AppShellMenu>
  </li>
</template>

<script setup lang="ts">
import DsIcon from "~/components/Design/DsIcon.vue";
import AppShellMenu from "~/components/Layout/AppShellMenu.vue";
import { freshnessLine, freshnessOf } from "~/lib/pantry/freshness";
import type { PantryItemOut } from "~/lib/api/types/household";
import type { AppShellMenuItem } from "~/types/application-types";

const props = defineProps<{
  item: PantryItemOut;
  today: Date;
}>();

const emit = defineEmits<{
  (e: "edit" | "opened" | "remove", item: PantryItemOut): void;
}>();

const i18n = useI18n();

const freshness = computed(() => freshnessOf(props.item, props.today));

/** "Worth checking", "Use soon"…: only when the item needs attention. */
const statusLabel = computed(() => {
  const status = freshness.value.status;
  return status === "past" || status === "check" || status === "soon" ? i18n.t(`pantry.status.${status}`) : "";
});

/** "Worth checking · opened 8 days ago": the status if any, then the use-by, opened or bought date. */
const meta = computed(() => {
  const text = freshnessLine(props.item, props.today, (key, params) => i18n.t(key, params ?? {}), i18n.locale.value)?.text
    ?? i18n.t("pantry.no-date");
  if (!statusLabel.value) {
    return text;
  }
  return `${statusLabel.value} · ${text.charAt(0).toLocaleLowerCase(i18n.locale.value)}${text.slice(1)}`;
});

/** "1 litre", "500 g", "3": the unit only when there is an amount to go with it. */
const qty = computed(() => {
  const quantity = props.item.quantity;
  if (!quantity) {
    return "";
  }
  const amount = new Intl.NumberFormat(i18n.locale.value, { maximumFractionDigits: 2 }).format(quantity);
  const unit = props.item.unit;
  const unitName = unit ? (quantity !== 1 && unit.pluralName ? unit.pluralName : unit.name) : "";
  return [amount, unitName].filter(Boolean).join(" ");
});

const actions = computed<AppShellMenuItem[]>(() => [
  { key: "opened", label: i18n.t("pantry.opened-today"), icon: "check", onSelect: () => emit("opened", props.item) },
  { key: "edit", label: i18n.t("pantry.edit"), icon: "edit", onSelect: () => emit("edit", props.item) },
  { key: "remove", label: i18n.t("pantry.remove"), icon: "delete", onSelect: () => emit("remove", props.item), dividerBefore: true },
]);
</script>

<style scoped>
.pantry-row {
  display: flex;
  align-items: center;
  min-height: 52px;
  border-bottom: 1px solid var(--ds-border);
}

.pantry-row:last-child {
  border-bottom: 0;
}

.pantry-row__main {
  display: flex;
  flex: 1;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  min-width: 0;
  min-height: 52px;
  padding: var(--ds-space) var(--ds-space) var(--ds-space) calc(var(--ds-space) * 0.5);
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.pantry-row__dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ds-have);
}

.pantry-row__dot--soon,
.pantry-row__dot--check {
  background: var(--ds-soon-bar);
}

.pantry-row__dot--past {
  background: var(--ds-missing);
}

/* No dates: a hollow ring, so "fine" is never claimed without evidence. */
.pantry-row__dot--unknown {
  background: transparent;
  box-shadow: inset 0 0 0 1.5px var(--ds-border);
}

.pantry-row__text {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
}

.pantry-row__name {
  font-size: var(--ds-t-3);
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.pantry-row__fresh {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  line-height: 1.3;
}

.pantry-row__fresh--soon,
.pantry-row__fresh--check {
  color: var(--ds-soon);
  font-weight: 600;
}

.pantry-row__fresh--past {
  color: var(--ds-missing);
  font-weight: 600;
}

.pantry-row__qty {
  flex: none;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
}

.pantry-row :deep(.pantry-row__more) {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text-2);
  cursor: pointer;
}

.pantry-row :deep(.pantry-row__more:hover) {
  color: var(--ds-text);
}

/* The open menu floats over the rows below it. */
.pantry-row__menu :deep(.ds-menu__list) {
  z-index: 3;
}

@media (min-width: 1024px) {
  .pantry-row,
  .pantry-row__main {
    min-height: 48px;
  }
}
</style>
