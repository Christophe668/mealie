<template>
  <section class="cook-ingredients" :aria-labelledby="headingId">
    <h2 :id="headingId" class="cook-ingredients__heading">
      {{ $t("cook.ingredients") }}
    </h2>
    <div v-for="(section, sIndex) in sections" :key="sIndex" class="cook-ingredients__section">
      <h3 v-if="section.title" class="cook-ingredients__section-title">
        {{ section.title }}
      </h3>
      <ul class="cook-ingredients__items" role="list">
        <li
          v-for="row in section.rows"
          :key="row.key"
          class="cook-ingredients__item"
          :class="{ 'cook-ingredients__item--active': row.active, 'checked': isChecked(row.key) }"
        >
          <input
            :id="`${headingId}-${row.index}`"
            type="checkbox"
            class="cook-ingredients__box ds-focus"
            :checked="isChecked(row.key)"
            @change="setChecked(row.key, ($event.target as HTMLInputElement).checked)"
          >
          <label :for="`${headingId}-${row.index}`" class="cook-ingredients__label">
            <!-- The shared parser sanitises its output, as on the read page. -->
            <!-- eslint-disable-next-line vue/no-v-html -->
            <span v-html="row.html" />
            <!-- eslint-disable-next-line vue/no-v-html -->
            <span v-if="row.note" class="cook-ingredients__note" v-html="` ${row.note}`" />
            <span v-if="row.active" class="cook-sr-only">, {{ $t("cook.in-this-step") }}</span>
          </label>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import { marked } from "marked";
import { ingredientTicksKey } from "~/components/Domain/Recipe/RecipeRead/RecipeReadIngredients.vue";
import { useIngredientTextParser } from "~/composables/recipes";
import { sanitizeMarkdownHtml } from "~/lib/sanitize/markdown";

const props = withDefaults(defineProps<{
  ingredients: RecipeIngredient[];
  /** Indexes of the ingredients the current step uses. */
  active?: number[];
  scale?: number;
  recipeSlug: string;
  groupSlug?: string;
}>(), {
  active: () => [],
  scale: 1,
  groupSlug: "",
});

const headingId = useId();
const { useParsedIngredientText } = useIngredientTextParser();

interface Row {
  key: string;
  index: number;
  html: string;
  note: string;
  active: boolean;
}

/* Same line as the read page: quantity, unit and food from the shared parser (so scaling and fractions match), then the note. */
function inlineMarkdown(source: string): string {
  return sanitizeMarkdownHtml(marked.parseInline(source, { async: false }) as string, []);
}

const join = (parts: (string | undefined)[]) => parts.filter(Boolean).join(" ");

function lineParts(ingredient: RecipeIngredient): Pick<Row, "html" | "note"> {
  const parsed = useParsedIngredientText(ingredient, props.scale, true, props.groupSlug);
  const note = ingredient.note?.trim() ? inlineMarkdown(ingredient.note) : "";
  const subject = parsed.recipeLink ? sanitizeMarkdownHtml(parsed.recipeLink, []) : parsed.name;
  if (!subject) {
    return { html: join([parsed.quantity, parsed.unit, note]), note: "" };
  }
  return { html: join([parsed.quantity, parsed.unit, subject]), note };
}

const sections = computed(() => {
  const active = new Set(props.active);
  const result: { title: string; rows: Row[] }[] = [];
  props.ingredients.forEach((ingredient, index) => {
    const title = ingredient.title?.trim() || "";
    if (title || !result.length) {
      result.push({ title, rows: [] });
    }
    result[result.length - 1]!.rows.push({
      key: ingredient.referenceId ? `ref:${ingredient.referenceId}` : `idx:${index}`,
      index,
      active: active.has(index),
      ...lineParts(ingredient),
    });
  });
  return result;
});

/* The read page's ticks, same key and shape, so a tick here shows there and back. */
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

<style scoped>
.cook-ingredients__heading {
  margin: 0 0 calc(var(--ds-space) * 1.5);
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

.cook-ingredients__section + .cook-ingredients__section {
  margin-top: calc(var(--ds-space) * 2.5);
}

.cook-ingredients__section-title {
  margin: 0 0 calc(var(--ds-space) * 0.5);
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 600;
}

.cook-ingredients__items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.cook-ingredients__item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: calc(var(--ds-space) * 1.5);
  padding: var(--ds-space) var(--ds-space) var(--ds-space) calc(var(--ds-space) * 1.5);
  border-bottom: 1px solid var(--ds-border);
  color: var(--ds-text-2);
}

.cook-ingredients__item:last-child {
  border-bottom: 0;
}

/* The screen's accent: a saffron bar beside what this step needs, its words at full strength. */
.cook-ingredients__item--active {
  color: var(--ds-text);
}

.cook-ingredients__item--active::before {
  position: absolute;
  top: 6px;
  bottom: 6px;
  left: 0;
  width: 4px;
  border-radius: 2px;
  background: var(--ds-accent);
  content: "";
}

.cook-ingredients__box {
  flex: none;
  width: 20px;
  height: 20px;
  margin: 2px 0 0;
  accent-color: var(--ds-text);
  cursor: pointer;
}

.cook-ingredients__label {
  flex: 1;
  min-width: 0;
  font-size: var(--ds-t-3);
  line-height: 1.45;
  cursor: pointer;
  overflow-wrap: anywhere;
}

.cook-ingredients__item--active .cook-ingredients__label {
  font-weight: 600;
}

.cook-ingredients__label :deep(sup),
.cook-ingredients__label :deep(sub) {
  font-size: 0.7em;
}

.cook-ingredients__note {
  color: var(--ds-text-2);
  font-weight: 400;
}

.cook-ingredients__label :deep(a) {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.checked .cook-ingredients__label {
  color: var(--ds-text-2);
  text-decoration: line-through;
  text-decoration-thickness: 1px;
}
</style>
