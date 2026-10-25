<template>
  <div class="profile-chips">
    <label :for="inputId" class="profile-chips__label">{{ label }}</label>
    <div class="profile-chips__box" @click="focus">
      <ul v-if="modelValue.length" class="profile-chips__list" role="list">
        <li v-for="chip in modelValue" :key="chip">
          <DsChip :tone="tone" class="profile-chips__chip">
            {{ chip }}
            <button
              type="button"
              class="profile-chips__remove ds-focus"
              :aria-label="$t('household-profile.remove-chip', { value: chip })"
              @click.stop="remove(chip)"
            >
              <DsIcon name="close" :size="14" />
            </button>
          </DsChip>
        </li>
      </ul>
      <input
        :id="inputId"
        ref="input"
        v-model="text"
        type="text"
        class="profile-chips__input"
        :placeholder="modelValue.length ? '' : $t('household-profile.chip-placeholder')"
        :maxlength="MAX_CHIP_LENGTH * MAX_CHIPS"
        autocomplete="off"
        enterkeyhint="done"
        :aria-describedby="hint ? hintId : undefined"
        @keydown.enter="onEnter"
        @blur="commit"
      >
    </div>
    <p :id="hintId" class="profile-chips__hint" aria-live="polite">
      {{ hint }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { useId, useTemplateRef } from "vue";
import DsChip from "~/components/Design/DsChip.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { addChips, MAX_CHIP_LENGTH, MAX_CHIPS } from "~/lib/household-profile/profile";

const props = withDefaults(defineProps<{
  modelValue: string[];
  label: string;
  /** accent = saffron; the household page spends it on allergies only. */
  tone?: "neutral" | "accent";
}>(), {
  tone: "neutral",
});

const emit = defineEmits<{ (e: "update:modelValue", value: string[]): void }>();

const i18n = useI18n();
const inputId = useId();
const hintId = useId();
const input = useTemplateRef<HTMLInputElement>("input");
const text = ref("");
/** Says why something typed was not (fully) added; cleared by the next keystroke. */
const hint = ref("");

function focus() {
  input.value?.focus();
}

/** Enter, a comma or leaving the field turns what was typed into chips. */
function commit() {
  if (!text.value.trim()) {
    text.value = "";
    return;
  }
  const { chips, rest, cut } = addChips(props.modelValue, text.value);
  // What did not fit stays in the field, so nothing typed is lost.
  text.value = rest.join(", ");
  hint.value = rest.length
    ? i18n.t("household-profile.chips-full", { count: MAX_CHIPS })
    : cut
      ? i18n.t("household-profile.chip-cut", { count: MAX_CHIP_LENGTH })
      : "";
  if (chips.length !== props.modelValue.length) {
    emit("update:modelValue", chips);
  }
}

/** Enter confirms an input method's composition (Japanese, Chinese…) first: only a plain Enter adds. */
function onEnter(event: KeyboardEvent) {
  if (event.isComposing || event.keyCode === 229) {
    return;
  }
  event.preventDefault();
  commit();
}

const commas = (value: string) => value.split(",").length - 1;

// A comma typed (or pasted) adds what is before it. Text put back by `commit` has no new comma, and shrinks.
watch(text, (value, before) => {
  if (commas(value) > commas(before)) {
    commit();
  }
  else if (value.length > before.length) {
    hint.value = "";
  }
});

function remove(chip: string) {
  emit("update:modelValue", props.modelValue.filter(value => value !== chip));
  focus();
}

defineExpose({ focus });
</script>

<style scoped>
.profile-chips {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.5);
  min-width: 0;
}

.profile-chips__label {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 500;
}

.profile-chips__box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: calc(var(--ds-space) * 0.75);
  min-height: 44px;
  padding: calc(var(--ds-space) * 0.75) var(--ds-space);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-bg);
  cursor: text;
}

.profile-chips__box:focus-within {
  border-color: var(--ds-text);
  outline: 2px solid var(--ds-text);
  outline-offset: 1px;
}

.profile-chips__list {
  display: contents;
  margin: 0;
  padding: 0;
  list-style: none;
}

.profile-chips__chip {
  max-width: 100%;
  white-space: normal;
  overflow-wrap: anywhere;
}

.profile-chips__remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  /* A 24px target inside a compact chip; the chip padding gives it room. */
  width: 24px;
  height: 24px;
  margin: calc(var(--ds-space) * -0.5) calc(var(--ds-space) * -0.75) calc(var(--ds-space) * -0.5) 0;
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: inherit;
  cursor: pointer;
}

.profile-chips__input {
  flex: 1 1 4ch;
  min-width: 4ch;
  min-height: 28px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-2);
  outline: none;
}

.profile-chips__hint {
  min-height: 0;
  margin: 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
}

.profile-chips__hint:empty {
  display: none;
}

.profile-chips__input::placeholder {
  color: var(--ds-text-2);
}
</style>
