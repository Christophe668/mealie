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
      <span>{{ item.label }}</span>
    </NuxtLink>

    <div v-if="addItems.length" ref="menuRoot" class="ds-tabbar__add">
      <button
        ref="trigger"
        type="button"
        class="ds-tabbar__plus ds-focus"
        aria-haspopup="menu"
        :aria-expanded="open ? 'true' : 'false'"
        :aria-controls="menuId"
        :aria-label="$t('app-shell.add')"
        @click="toggle"
      >
        <DsIcon name="createAlt" :size="26" />
      </button>

      <ul
        v-if="open"
        :id="menuId"
        role="menu"
        class="ds-tabbar__menu"
        :aria-label="$t('app-shell.add')"
        @keydown="onMenuKeydown"
      >
        <li v-for="item in addItems" :key="item.key" role="none">
          <NuxtLink
            ref="menuItems"
            :to="item.to"
            role="menuitem"
            tabindex="-1"
            class="ds-tabbar__menuitem"
            @click="close(false)"
          >
            <DsIcon :name="item.icon" :size="20" />
            {{ item.label }}
          </NuxtLink>
        </li>
      </ul>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { nextTick, useId, useTemplateRef } from "vue";
import { onClickOutside } from "@vueuse/core";
import DsIcon from "~/components/Design/DsIcon.vue";
import type { AppShellNavItem } from "~/types/application-types";

const props = defineProps<{
  items: AppShellNavItem[];
  addItems: Omit<AppShellNavItem, "active">[];
  /** Changes on navigation; an open menu closes when the page changes. */
  routePath: string;
}>();

const menuId = useId();
const open = ref(false);
const trigger = useTemplateRef<HTMLButtonElement>("trigger");
const menuRoot = useTemplateRef<HTMLElement>("menuRoot");
const menuItems = useTemplateRef<Array<{ $el: HTMLElement } | HTMLElement>>("menuItems");

function itemElements(): HTMLElement[] {
  return (menuItems.value ?? []).map(item => (item instanceof HTMLElement ? item : item.$el));
}

function focusItem(index: number) {
  const elements = itemElements();
  if (!elements.length) {
    return;
  }
  const wrapped = (index + elements.length) % elements.length;
  elements[wrapped]!.focus();
}

async function openMenu() {
  open.value = true;
  await nextTick();
  focusItem(0);
}

function close(returnFocus = true) {
  if (!open.value) {
    return;
  }
  open.value = false;
  if (returnFocus) {
    trigger.value?.focus();
  }
}

function toggle() {
  if (open.value) {
    close();
  }
  else {
    openMenu();
  }
}

function onMenuKeydown(event: KeyboardEvent) {
  const current = itemElements().indexOf(document.activeElement as HTMLElement);
  switch (event.key) {
    case "Escape":
      event.preventDefault();
      close();
      break;
    case "ArrowDown":
      event.preventDefault();
      focusItem(current + 1);
      break;
    case "ArrowUp":
      event.preventDefault();
      focusItem(current - 1);
      break;
    case "Home":
      event.preventDefault();
      focusItem(0);
      break;
    case "End":
      event.preventDefault();
      focusItem(-1);
      break;
    case "Tab":
      close(false);
      break;
  }
}

onClickOutside(menuRoot, () => close(false));
watch(() => props.routePath, () => close(false));
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
  flex: 1;
  flex-direction: column;
  align-items: center;
  gap: calc(var(--ds-space) * 0.25);
  min-width: 0;
  padding: calc(var(--ds-space) * 0.75) calc(var(--ds-space) * 0.5);
  border-radius: var(--ds-radius-ctl);
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 500;
  text-decoration: none;
}

.ds-tabbar__link[aria-current="page"] {
  background: var(--ds-bg);
  color: var(--ds-text);
  font-weight: 700;
}

.ds-tabbar__add {
  position: relative;
  flex: none;
}

/* Ink, not saffron: Home's Tonight board is the screen's single accent. */
.ds-tabbar__plus {
  display: grid;
  place-items: center;
  width: calc(var(--ds-space) * 6.5);
  height: calc(var(--ds-space) * 6.5);
  border: 0;
  border-radius: var(--ds-radius-card);
  background: var(--ds-text);
  color: var(--ds-bg);
  cursor: pointer;
}

.ds-tabbar__menu {
  position: absolute;
  right: 0;
  bottom: calc(100% + var(--ds-space) * 1.5);
  min-width: calc(var(--ds-space) * 30);
  margin: 0;
  padding: calc(var(--ds-space) * 0.75);
  list-style: none;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  background: var(--ds-surface);
  box-shadow: var(--ds-shadow-float);
  animation: ds-menu-in 140ms ease-out;
}

.ds-tabbar__menuitem {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  padding: calc(var(--ds-space) * 1.5);
  border-radius: var(--ds-radius-ctl);
  color: var(--ds-text);
  font-size: var(--ds-t-2);
  font-weight: 500;
  text-decoration: none;
  outline: none;
}

.ds-tabbar__menuitem:hover,
.ds-tabbar__menuitem:focus-visible {
  background: var(--ds-bg);
}

.ds-tabbar__menuitem:focus-visible {
  outline: 2px solid var(--ds-text);
  outline-offset: -2px;
}

@keyframes ds-menu-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .ds-tabbar__menu {
    animation: none;
  }
}
</style>
