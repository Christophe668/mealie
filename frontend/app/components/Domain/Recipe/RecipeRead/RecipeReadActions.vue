<template>
  <div class="read-actions d-print-none" role="group" :aria-label="$t('recipe-read.actions')">
    <DsButton v-if="canEdit" variant="line" icon="edit" @click="emit('edit')">
      {{ $t("recipe-read.edit") }}
    </DsButton>
    <DsButton v-if="loggedIn" variant="line" icon="calendar" @click="emit('plan')">
      {{ $t("recipe-read.add-to-plan") }}
    </DsButton>
    <DsButton v-if="loggedIn" variant="line" icon="cartCheck" @click="emit('list')">
      {{ $t("recipe-read.add-to-list") }}
    </DsButton>
    <AppShellMenu
      v-if="moreItems.length > 1"
      :items="moreItems"
      :label="$t('recipe-read.more-actions')"
      :trigger-label="$t('recipe-read.more-actions')"
      trigger-class="read-actions__more ds-focus"
      placement="bottom-end"
    >
      <template #trigger>
        <DsIcon name="dotsVertical" :size="20" />
      </template>
    </AppShellMenu>
    <!-- Visitors only get Print, so it stands on its own instead of hiding in a one-item menu. -->
    <DsButton v-else variant="line" icon="printer" @click="emit('print')">
      {{ $t("recipe-read.print") }}
    </DsButton>
  </div>
</template>

<script setup lang="ts">
import DsButton from "~/components/Design/DsButton.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import AppShellMenu from "~/components/Layout/AppShellMenu.vue";
import type { AppShellMenuItem } from "~/types/application-types";

const props = withDefaults(defineProps<{
  /** Signed in to the recipe's group: plan, list and share need it. */
  loggedIn?: boolean;
  canEdit?: boolean;
  canDelete?: boolean;
}>(), {
  loggedIn: false,
  canEdit: false,
  canDelete: false,
});

const emit = defineEmits<{
  (e: "edit" | "plan" | "list" | "share" | "print" | "delete"): void;
}>();

const i18n = useI18n();

const moreItems = computed<AppShellMenuItem[]>(() => {
  const items: AppShellMenuItem[] = [];
  if (props.loggedIn) {
    items.push({ key: "share", label: i18n.t("recipe-read.share"), icon: "shareVariant", onSelect: () => emit("share") });
  }
  items.push({ key: "print", label: i18n.t("recipe-read.print"), icon: "printer", onSelect: () => emit("print") });
  if (props.canDelete) {
    items.push({ key: "delete", label: i18n.t("recipe-read.delete"), icon: "delete", dividerBefore: true, onSelect: () => emit("delete") });
  }
  return items;
});
</script>

<style scoped>
.read-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ds-space);
}

.read-actions :deep(.read-actions__more) {
  display: grid;
  place-items: center;
  width: calc(var(--ds-space) * 5);
  height: calc(var(--ds-space) * 5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  cursor: pointer;
}
</style>
