<template>
  <component
    :is="mobile ? VBottomSheet : VDialog"
    v-model="open"
    :persistent="busy"
    :max-width="mobile ? undefined : 440"
    :aria-label="title"
  >
    <div class="ds-sheet" :aria-busy="busy" @keydown.esc="onEscape">
      <span v-if="mobile" class="ds-sheet__handle" aria-hidden="true" />
      <slot name="header">
        <h2 class="ds-sheet__title">
          {{ title }}
        </h2>
      </slot>
      <slot />
    </div>
  </component>
</template>

<script setup lang="ts">
import { useDisplay } from "vuetify";
import { VBottomSheet, VDialog } from "vuetify/components";
import { useFocusReturn } from "~/composables/use-focus-return";

const props = withDefaults(defineProps<{
  title: string;
  /** A request is in flight: Escape and the scrim stop closing the sheet. */
  busy?: boolean;
  /** Where focus goes on close when the element that opened the sheet is gone by then (an action removed it). */
  fallback?: () => HTMLElement | null | undefined;
}>(), {
  busy: false,
  fallback: undefined,
});

const open = defineModel<boolean>({ default: false });
// Opened through v-model, so Vuetify has no activator to give focus back to.
useFocusReturn(open, () => props.fallback?.());
const { mobile } = useDisplay();

function onEscape() {
  if (!props.busy) {
    open.value = false;
  }
}
</script>

<style scoped>
.ds-sheet {
  display: flex;
  flex-direction: column;
  background: var(--ds-surface);
  color: var(--ds-text);
  padding: calc(var(--ds-space) * 2);
  padding-bottom: max(calc(var(--ds-space) * 2), env(safe-area-inset-bottom));
  border-radius: var(--ds-radius-card);
}

/* Bottom sheet on mobile: rounded on top only, with a grab handle. */
.v-bottom-sheet .ds-sheet {
  border-radius: 18px 18px 0 0;
}

.ds-sheet__handle {
  align-self: center;
  width: 36px;
  height: 4px;
  margin-bottom: var(--ds-space);
  border-radius: 2px;
  background: var(--ds-border);
}

.ds-sheet__title {
  margin: 0;
  font-size: var(--ds-t-4);
  font-weight: 700;
  line-height: 1.25;
}

/* Action rows, for the sheet body: <button class="ds-sheet__action"> icon, label, optional hint. */
.ds-sheet :deep(.ds-sheet__action) {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  width: 100%;
  min-height: 48px;
  padding: var(--ds-space) 0;
  border: 0;
  border-top: 1px solid var(--ds-border);
  background: none;
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-2);
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.ds-sheet :deep(.ds-sheet__action:focus-visible) {
  outline: 2px solid var(--ds-text);
  outline-offset: -2px;
}

.ds-sheet :deep(.ds-sheet__action[disabled]),
.ds-sheet :deep(.ds-sheet__action[aria-disabled="true"]) {
  opacity: 0.5;
  cursor: default;
}

.ds-sheet :deep(.ds-sheet__action .v-icon) {
  box-sizing: content-box;
  padding: 6px;
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-bg);
}

.ds-sheet :deep(.ds-sheet__hint) {
  display: block;
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 400;
}

.ds-sheet :deep(.ds-sheet__action--danger) {
  color: var(--ds-missing);
}
</style>
