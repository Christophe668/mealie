<template>
  <div ref="root" class="ds-menu">
    <button
      ref="trigger"
      type="button"
      :class="triggerClass"
      aria-haspopup="menu"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-controls="menuId"
      :aria-label="triggerLabel"
      @click="toggle"
    >
      <slot name="trigger" />
    </button>

    <ul
      v-if="open"
      :id="menuId"
      role="menu"
      class="ds-menu__list"
      :class="`ds-menu__list--${placement}`"
      :aria-label="label"
      @keydown="onKeydown"
    >
      <li
        v-for="(item, index) in items"
        :key="item.key"
        role="none"
        :class="{ 'ds-menu__group': item.dividerBefore }"
      >
        <NuxtLink
          v-if="item.to"
          :ref="(el) => setItemRef(el, index)"
          :to="item.to"
          role="menuitem"
          tabindex="-1"
          class="ds-menu__item"
          @click="close(false)"
        >
          <DsIcon :name="item.icon" :size="20" />
          {{ item.label }}
        </NuxtLink>
        <button
          v-else
          :ref="(el) => setItemRef(el, index)"
          type="button"
          :role="item.checked === undefined ? 'menuitem' : 'menuitemradio'"
          :aria-checked="item.checked === undefined ? undefined : String(item.checked)"
          tabindex="-1"
          class="ds-menu__item"
          @click="select(item)"
        >
          <DsIcon :name="item.icon" :size="20" />
          {{ item.label }}
          <DsIcon v-if="item.checked" class="ds-menu__check" name="check" :size="18" />
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { nextTick, useId, useTemplateRef } from "vue";
import type { ComponentPublicInstance } from "vue";
import { onClickOutside } from "@vueuse/core";
import DsIcon from "~/components/Design/DsIcon.vue";
import type { AppShellMenuItem } from "~/types/application-types";

withDefaults(defineProps<{
  items: AppShellMenuItem[];
  /** Accessible name of the menu. */
  label: string;
  /** Accessible name of the trigger, when its slot content has no visible text. */
  triggerLabel?: string;
  triggerClass?: string;
  /** Which way the list opens, relative to the trigger. */
  placement?: "top-start" | "top-end" | "bottom-end";
}>(), {
  triggerLabel: undefined,
  triggerClass: undefined,
  placement: "bottom-end",
});

const menuId = useId();
const open = ref(false);
const trigger = useTemplateRef<HTMLButtonElement>("trigger");
const root = useTemplateRef<HTMLElement>("root");
const itemRefs: HTMLElement[] = [];

function setItemRef(el: Element | ComponentPublicInstance | null, index: number) {
  if (el) {
    itemRefs[index] = (el instanceof Element ? el : el.$el) as HTMLElement;
  }
}

function focusItem(index: number) {
  const elements = itemRefs.filter(Boolean);
  if (!elements.length) {
    return;
  }
  elements[(index + elements.length) % elements.length]!.focus();
}

async function openMenu() {
  itemRefs.length = 0;
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

function select(item: AppShellMenuItem) {
  close();
  item.onSelect?.();
}

function onKeydown(event: KeyboardEvent) {
  const current = itemRefs.indexOf(document.activeElement as HTMLElement);
  const moves: Record<string, () => void> = {
    ArrowDown: () => focusItem(current + 1),
    ArrowUp: () => focusItem(current - 1),
    Home: () => focusItem(0),
    End: () => focusItem(-1),
    Escape: () => close(),
  };
  if (event.key === "Tab") {
    close(false);
    return;
  }
  const move = moves[event.key];
  if (move) {
    event.preventDefault();
    move();
  }
}

onClickOutside(root, () => close(false));
</script>

<style scoped>
.ds-menu {
  position: relative;
}

.ds-menu__list {
  position: absolute;
  z-index: 1;
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

.ds-menu__list--top-start {
  bottom: calc(100% + var(--ds-space));
  left: 0;
}

.ds-menu__list--top-end {
  right: 0;
  bottom: calc(100% + var(--ds-space) * 1.5);
}

.ds-menu__list--bottom-end {
  top: calc(100% + var(--ds-space));
  right: 0;
}

.ds-menu__group {
  margin-top: calc(var(--ds-space) * 0.75);
  padding-top: calc(var(--ds-space) * 0.75);
  border-top: 1px solid var(--ds-border);
}

.ds-menu__item {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  width: 100%;
  padding: calc(var(--ds-space) * 1.5);
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-2);
  font-weight: 500;
  text-align: left;
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
  outline: none;
}

.ds-menu__item:hover,
.ds-menu__item:focus-visible {
  background: var(--ds-bg);
}

.ds-menu__item:focus-visible {
  outline: 2px solid var(--ds-text);
  outline-offset: -2px;
}

.ds-menu__check {
  margin-left: auto;
}

@keyframes ds-menu-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .ds-menu__list {
    animation: none;
  }
}
</style>
