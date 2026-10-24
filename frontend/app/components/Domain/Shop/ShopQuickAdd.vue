<template>
  <form class="shop-quick-add" :aria-label="$t('shop.add-item')" @submit.prevent="submit">
    <label :for="inputId" class="shop-quick-add__sr">{{ $t("shop.add-item") }}</label>
    <DsIcon name="createAlt" :size="20" class="shop-quick-add__icon" />
    <input
      :id="inputId"
      ref="input"
      v-model="text"
      type="text"
      class="shop-quick-add__input"
      :placeholder="$t('shop.add-item')"
      autocomplete="off"
      enterkeyhint="done"
    >
    <DsButton variant="dark" class="shop-quick-add__submit" :disabled="!text.trim()" @click="submit">
      {{ $t("shop.add") }}
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
</script>

<style scoped>
.shop-quick-add {
  display: flex;
  align-items: center;
  gap: var(--ds-space);
  padding: calc(var(--ds-space) * 0.75) calc(var(--ds-space) * 0.75) calc(var(--ds-space) * 0.75)
    calc(var(--ds-space) * 1.75);
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.shop-quick-add:focus-within {
  border-color: var(--ds-text);
}

.shop-quick-add__icon {
  color: var(--ds-text-2);
}

.shop-quick-add__input {
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

.shop-quick-add__input::placeholder {
  color: var(--ds-text-2);
}

.shop-quick-add__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
