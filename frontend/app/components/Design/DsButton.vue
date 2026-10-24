<template>
  <NuxtLink
    v-if="to && !disabled"
    :to="to"
    :class="classes"
  >
    <DsIcon v-if="icon" :name="icon" :size="iconSize" />
    <slot />
  </NuxtLink>
  <button
    v-else
    :type="type"
    :class="classes"
    :aria-disabled="disabled ? 'true' : undefined"
    @click="swallowWhenDisabled"
  >
    <DsIcon v-if="icon" :name="icon" :size="iconSize" />
    <slot />
  </button>
</template>

<script setup lang="ts">
import DsIcon from "./DsIcon.vue";
import type { Icon } from "~/lib/icons/icon-type";

const props = withDefaults(defineProps<{
  /** primary = saffron (counts as the screen's one accent), dark = ink, line = surface + hairline, ghost = transparent. */
  variant?: "primary" | "dark" | "line" | "ghost";
  size?: "md" | "lg";
  to?: string;
  icon?: keyof Icon;
  block?: boolean;
  /** Uses aria-disabled rather than the native attribute so the button stays focusable and announced. */
  disabled?: boolean;
  /** Native button type; "submit" lets a form submit on Enter. Ignored for links. */
  type?: "button" | "submit";
}>(), {
  variant: "primary",
  size: "md",
  to: undefined,
  icon: undefined,
  block: false,
  disabled: false,
  type: "button",
});

const classes = computed(() => [
  "ds-btn",
  "ds-focus",
  `ds-btn--${props.variant}`,
  `ds-btn--${props.size}`,
  { "ds-btn--block": props.block },
]);

const iconSize = computed(() => (props.size === "lg" ? 20 : 18));

// Own listeners run before fall-through ones, and Vue honours stopImmediatePropagation across them.
function swallowWhenDisabled(event: MouseEvent) {
  if (props.disabled) {
    event.preventDefault();
    event.stopImmediatePropagation();
  }
}
</script>

<style scoped>
.ds-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--ds-space);
  border: 1px solid transparent;
  border-radius: var(--ds-radius-ctl);
  font-family: var(--ds-font);
  font-size: var(--ds-t-2);
  font-weight: 600;
  line-height: 1.2;
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background-color 120ms ease,
    border-color 120ms ease,
    opacity 120ms ease;
}

.ds-btn--md {
  min-height: calc(var(--ds-space) * 5);
  padding: calc(var(--ds-space) * 1.25) calc(var(--ds-space) * 1.75);
}

.ds-btn--lg {
  min-height: calc(var(--ds-space) * 6);
  padding: calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 2.5);
  font-size: var(--ds-t-3);
}

.ds-btn--block {
  display: flex;
  width: 100%;
}

.ds-btn--primary {
  background: var(--ds-accent);
  color: var(--ds-accent-text);
}

.ds-btn--dark {
  background: var(--ds-text);
  color: var(--ds-bg);
}

.ds-btn--line {
  background: var(--ds-surface);
  border-color: var(--ds-border);
  color: var(--ds-text);
}

.ds-btn--ghost {
  background: transparent;
  border-color: color-mix(in srgb, currentColor 35%, transparent);
  color: inherit;
}

.ds-btn:hover:not([aria-disabled="true"]) {
  opacity: 0.88;
}

.ds-btn[aria-disabled="true"] {
  cursor: not-allowed;
  opacity: 0.45;
}

@media (prefers-reduced-motion: reduce) {
  .ds-btn {
    transition: none;
  }
}
</style>
