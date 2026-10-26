<template>
  <nav class="ds-tabbar" :aria-label="$t('app-shell.main-navigation')">
    <NuxtLink
      v-for="item in items"
      :key="item.key"
      :to="item.to"
      class="ds-tabbar__link ds-focus"
      :aria-current="item.active ? 'page' : undefined"
    >
      <DsIcon :name="item.icon" :size="22" />
      <span class="ds-tabbar__label">{{ item.shortLabel || item.label }}</span>
    </NuxtLink>
  </nav>
</template>

<script setup lang="ts">
import DsIcon from "~/components/Design/DsIcon.vue";
import type { AppShellNavItem } from "~/types/application-types";

defineProps<{
  items: AppShellNavItem[];
}>();
</script>

<style scoped>
.ds-tabbar {
  position: fixed;
  right: calc(var(--ds-space) * 1.5);
  bottom: calc(var(--ds-space) * 1.5 + env(safe-area-inset-bottom));
  left: calc(var(--ds-space) * 1.5);
  /* Above page content and Vuetify app bars (1004), below Vuetify overlays and dialogs. */
  z-index: 1005;
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 0.5);
  padding: calc(var(--ds-space) * 0.75);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  background: var(--ds-surface);
  box-shadow: var(--ds-shadow-float);
}

.ds-tabbar__link {
  display: flex;
  /* Sized by the label, so a long one ("Recipes", "Aujourd’hui") takes room from the short ones. */
  flex: 1 1 auto;
  flex-direction: column;
  align-items: center;
  gap: calc(var(--ds-space) * 0.25);
  min-width: 0;
  padding: calc(var(--ds-space) * 0.75) 2px;
  border-radius: var(--ds-radius-ctl);
  color: var(--ds-text-2);
  font-size: 0.75rem;
  font-weight: 500;
  text-decoration: none;
}

/* A long translation shortens rather than pushes the add button off screen. */
.ds-tabbar__label {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ds-tabbar__link[aria-current="page"] {
  background: var(--ds-bg);
  color: var(--ds-text);
  font-weight: 700;
}
</style>
