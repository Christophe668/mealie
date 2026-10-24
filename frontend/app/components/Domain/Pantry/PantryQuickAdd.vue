<template>
  <form class="pantry-quick-add" :aria-label="$t('pantry.add-item')" @submit.prevent="submit">
    <label :for="inputId" class="pantry-quick-add__sr">{{ $t("pantry.add-item") }}</label>
    <DsIcon name="createAlt" :size="20" class="pantry-quick-add__icon" />
    <input
      :id="inputId"
      ref="input"
      v-model="text"
      type="text"
      class="pantry-quick-add__input"
      :placeholder="$t('pantry.add-item')"
      autocomplete="off"
      enterkeyhint="done"
    >
    <DsButton variant="dark" :disabled="!text.trim()" @click="submit">
      {{ $t("pantry.add") }}
    </DsButton>
  </form>
</template>

<script setup lang="ts">
import { useId, useTemplateRef } from "vue";
import DsButton from "~/components/Design/DsButton.vue";
import DsIcon from "~/components/Design/DsIcon.vue";

const emit = defineEmits<{ (e: "add", text: string): void }>();

const inputId = useId();
const input = useTemplateRef<HTMLInputElement>("input");
const text = ref("");

function submit() {
  const value = text.value.trim();
  if (!value) {
    return;
  }
  emit("add", value);
  text.value = "";
  // Stay in the field so a run of items can be typed one after another.
  input.value?.focus();
}

defineExpose({ focus: () => input.value?.focus() });
</script>

<style scoped>
.pantry-quick-add {
  display: flex;
  align-items: center;
  gap: var(--ds-space);
  padding: calc(var(--ds-space) * 0.75) calc(var(--ds-space) * 0.75) calc(var(--ds-space) * 0.75)
    calc(var(--ds-space) * 1.75);
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
}

/* The input drops its own outline; the whole field takes the same 2 px ring as .ds-focus. */
.pantry-quick-add:focus-within {
  border-color: var(--ds-text);
  outline: 2px solid var(--ds-text);
  outline-offset: 2px;
}

.pantry-quick-add__icon {
  color: var(--ds-text-2);
}

.pantry-quick-add__input {
  flex: 1;
  min-width: 0;
  min-height: 40px;
  padding: 0;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-3);
}

.pantry-quick-add__input::placeholder {
  color: var(--ds-text-2);
}

.pantry-quick-add__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
