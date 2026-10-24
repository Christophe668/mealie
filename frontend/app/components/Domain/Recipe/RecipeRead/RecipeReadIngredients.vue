<template>
  <section class="read-ingredients" :aria-labelledby="headingId">
    <h2 :id="headingId" class="read-ingredients__heading">
      <button
        v-if="collapsible"
        type="button"
        class="read-ingredients__toggle ds-focus"
        :aria-expanded="open ? 'true' : 'false'"
        :aria-controls="listId"
        @click="open = !open"
      >
        {{ $t("recipe-read.ingredients") }}
        <DsIcon name="chevronDown" :size="22" class="read-ingredients__chevron" :class="{ 'read-ingredients__chevron--open': open }" />
      </button>
      <template v-else>
        {{ $t("recipe-read.ingredients") }}
      </template>
    </h2>

    <div v-show="open || !collapsible" :id="listId" class="read-ingredients__list">
      <div
        v-for="(section, sIndex) in sections"
        :key="sIndex"
        class="read-ingredients__section"
      >
        <h3 v-if="section.title" class="read-ingredients__section-title">
          {{ section.title }}
        </h3>
        <ul class="read-ingredients__items" role="list">
          <li
            v-for="row in section.rows"
            :key="row.key"
            class="read-ingredients__item"
            :class="{ checked: isChecked(row.key) }"
          >
            <input
              :id="`${listId}-${row.index}`"
              type="checkbox"
              class="read-ingredients__box ds-focus"
              :checked="isChecked(row.key)"
              @change="setChecked(row.key, ($event.target as HTMLInputElement).checked)"
            >
            <!-- The parser sanitises its output (quantities carry <sup> fractions). -->
            <label :for="`${listId}-${row.index}`" class="read-ingredients__label">
              <!-- eslint-disable-next-line vue/no-v-html -->
              <span v-html="row.html" />
              <!-- eslint-disable-next-line vue/no-v-html -->
              <span v-if="row.note" class="read-ingredients__note" v-html="` ${row.note}`" />
            </label>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { useIngredientTextParser } from "~/composables/recipes";
import { marked } from "marked";
import type { RecipeIngredient } from "~/lib/api/types/recipe";
import { sanitizeMarkdownHtml } from "~/lib/sanitize/markdown";

const props = withDefaults(defineProps<{
  ingredients: RecipeIngredient[];
  scale?: number;
  recipeSlug: string;
  /** For links to referenced sub-recipes. */
  groupSlug?: string;
  /** Mobile: the heading becomes a disclosure button, open by default. */
  collapsible?: boolean;
}>(), {
  scale: 1,
  groupSlug: "",
  collapsible: false,
});

const headingId = useId();
const listId = useId();
const open = ref(true);

const { useParsedIngredientText } = useIngredientTextParser();

interface Row {
  key: string;
  index: number;
  html: string;
  note: string;
}

/** Notes are markdown upstream (SafeMarkdown); inline here so the line keeps flowing. */
function inlineMarkdown(source: string): string {
  return sanitizeMarkdownHtml(marked.parseInline(source, { async: false }) as string, []);
}

const join = (parts: (string | undefined)[]) => parts.filter(Boolean).join(" ");

/**
 * Quantity, unit and food (or the linked sub-recipe) in ink, from the shared parser so scaling and
 * fractions match upstream; the note ("halved", "about 1.6 kg") follows in the secondary colour.
 */
function lineParts(ingredient: RecipeIngredient): Pick<Row, "html" | "note"> {
  const parsed = useParsedIngredientText(ingredient, props.scale, true, props.groupSlug);
  const note = ingredient.note?.trim() ? inlineMarkdown(ingredient.note) : "";
  const subject = parsed.recipeLink ? sanitizeMarkdownHtml(parsed.recipeLink, []) : parsed.name;
  if (!subject) {
    // An unparsed line keeps all its words in the note, so the note is the ingredient.
    return { html: join([parsed.quantity, parsed.unit, note]), note: "" };
  }
  return { html: join([parsed.quantity, parsed.unit, subject]), note };
}

const sections = computed(() => {
  const result: { title: string; rows: Row[] }[] = [];
  props.ingredients.forEach((ingredient, index) => {
    const title = ingredient.title?.trim() || "";
    if (title || !result.length) {
      result.push({ title, rows: [] });
    }
    result[result.length - 1]!.rows.push({
      // The reference id survives reordering in the editor; the index is the fallback.
      key: ingredient.referenceId ? `ref:${ingredient.referenceId}` : `idx:${index}`,
      index,
      ...lineParts(ingredient),
    });
  });
  return result;
});

// Read again whenever the slug changes, so moving between recipes never carries ticks across.
const ticks = ref<Record<string, boolean>>({});
watch(
  () => props.recipeSlug,
  (slug) => {
    try {
      ticks.value = JSON.parse(sessionStorage.getItem(ingredientTicksKey(slug)) || "{}") || {};
    }
    catch {
      ticks.value = {};
    }
  },
  { immediate: true },
);

function isChecked(key: string) {
  return !!ticks.value[key];
}

function setChecked(key: string, value: boolean) {
  const rest = Object.entries(ticks.value).filter(([k]) => k !== key);
  ticks.value = Object.fromEntries(value ? [...rest, [key, true]] : rest);
  try {
    sessionStorage.setItem(ingredientTicksKey(props.recipeSlug), JSON.stringify(ticks.value));
  }
  catch {
    // Private mode or a full quota: ticks still work for this visit.
  }
}
</script>

<script lang="ts">
/** Session-storage key for the ticked ingredients of one recipe; cook mode reads the same ticks. */
export function ingredientTicksKey(recipeSlug: string): string {
  return `recipe-read:${recipeSlug}:ticked`;
}
</script>

<style scoped>
.read-ingredients__heading {
  margin: 0 0 calc(var(--ds-space) * 1.5);
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

.read-ingredients__toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: calc(var(--ds-space) * 5.5);
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: inherit;
  font: inherit;
  letter-spacing: inherit;
  text-align: left;
  cursor: pointer;
}

.read-ingredients__chevron {
  transition: transform 160ms ease;
}

.read-ingredients__chevron--open {
  transform: rotate(180deg);
}

.read-ingredients__section + .read-ingredients__section {
  margin-top: calc(var(--ds-space) * 2.5);
}

.read-ingredients__section-title {
  margin: 0 0 calc(var(--ds-space) * 0.5);
  font-size: var(--ds-t-2);
  font-weight: 600;
  color: var(--ds-text-2);
}

.read-ingredients__items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.read-ingredients__item {
  display: flex;
  align-items: flex-start;
  gap: calc(var(--ds-space) * 1.5);
  padding: var(--ds-space) 0;
  border-bottom: 1px solid var(--ds-border);
}

.read-ingredients__item:last-child {
  border-bottom: 0;
}

.read-ingredients__box {
  flex: none;
  width: 20px;
  height: 20px;
  margin: 2px 0 0;
  accent-color: var(--ds-text);
  cursor: pointer;
}

.read-ingredients__label {
  flex: 1;
  min-width: 0;
  font-size: var(--ds-t-3);
  line-height: 1.45;
  cursor: pointer;
  overflow-wrap: anywhere;
}

.read-ingredients__label :deep(sup),
.read-ingredients__label :deep(sub) {
  font-size: 0.7em;
}

.read-ingredients__note {
  color: var(--ds-text-2);
}

.read-ingredients__label :deep(a) {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.checked .read-ingredients__label {
  text-decoration: line-through;
  text-decoration-thickness: 1px;
  color: var(--ds-text-2);
}

@media (prefers-reduced-motion: reduce) {
  .read-ingredients__chevron {
    transition: none;
  }
}
</style>
