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
      <div v-if="summary" class="read-ingredients__summary">
        <i18n-t keypath="recipe-read.pantry-summary" tag="p" class="read-ingredients__summary-text">
          <template #counts>
            <strong>{{ $t("recipe-read.pantry-counts", { have: summary.have, total: summary.total }) }}</strong>
          </template>
        </i18n-t>
        <DsButton v-if="summary.missing.length && canAct" variant="dark" @click="emit('add-missing', summary.missing)">
          {{ $t("recipe-read.add-missing", { count: summary.missing.length }) }}
        </DsButton>
      </div>
      <div
        v-for="(section, sIndex) in sections"
        :key="sIndex"
        class="read-ingredients__section"
      >
        <h3 v-if="section.title" class="read-ingredients__section-title">
          {{ section.title }}
        </h3>
        <ul class="read-ingredients__items" role="list">
          <li v-for="row in section.rows" :key="row.key" class="read-ingredients__item">
            <component
              :is="row.status && canAct ? 'button' : 'div'"
              :type="row.status && canAct ? 'button' : undefined"
              class="read-ingredients__row"
              :class="{ 'read-ingredients__row--action': row.status && canAct, 'ds-focus': row.status && canAct }"
              @click="row.status && canAct && emit('open-ingredient', { ingredient: row.ingredient, items: row.items })"
            >
              <span
                class="read-ingredients__bar"
                :class="row.status && `read-ingredients__bar--${row.status}`"
                aria-hidden="true"
              />
              <span class="read-ingredients__body">
                <span class="read-ingredients__label">
                  <!-- The parser sanitises its output (quantities carry <sup> fractions). -->
                  <!-- eslint-disable-next-line vue/no-v-html -->
                  <span v-html="row.html" />
                  <!-- eslint-disable-next-line vue/no-v-html -->
                  <span v-if="row.note" class="read-ingredients__note" v-html="` ${row.note}`" />
                </span>
                <span v-if="row.detail" class="read-ingredients__detail">{{ row.detail }}</span>
              </span>
              <span v-if="row.status" class="read-ingredients__tag" :class="`read-ingredients__tag--${row.status}`">
                <DsIcon :name="STATUS_ICON[row.status]" :size="14" />
                {{ $t(`recipe-read.status-${row.status}`) }}
              </span>
            </component>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import type { IngredientPantry } from "~/composables/use-recipe-pantry";
import type { PantryItemOut } from "~/lib/api/types/household";
import { type IngredientStatus, ingredientStatus, pantryDetail } from "~/lib/pantry/ingredient-status";
import DsButton from "~/components/Design/DsButton.vue";
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
  /** The household's pantry per ingredient; null leaves the pantry out (unknown, or a visitor). */
  pantry?: IngredientPantry | null;
  /** Rows with a status open the ingredient's actions; members with a known pantry only. */
  canAct?: boolean;
}>(), {
  scale: 1,
  groupSlug: "",
  collapsible: false,
  pantry: null,
  canAct: false,
});

const emit = defineEmits<{
  "open-ingredient": [payload: { ingredient: RecipeIngredient; items: PantryItemOut[] }];
  "add-missing": [ingredients: RecipeIngredient[]];
}>();

const STATUS_ICON = { have: "checkboxMarkedCircle", soon: "alertCircle", missing: "minusCircle" } as const;

const i18n = useI18n();

const headingId = useId();
const listId = useId();
const open = ref(true);

const { useParsedIngredientText } = useIngredientTextParser();

interface Row {
  key: string;
  ingredient: RecipeIngredient;
  html: string;
  note: string;
  /** Absent when the pantry is unknown or the ingredient names no food. */
  status: IngredientStatus | null;
  items: PantryItemOut[];
  /** "Fridge · Use by October 25"; empty when missing. */
  detail: string;
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
  const today = new Date();
  const result: { title: string; rows: Row[] }[] = [];
  props.ingredients.forEach((ingredient, index) => {
    const title = ingredient.title?.trim() || "";
    if (title || !result.length) {
      result.push({ title, rows: [] });
    }
    const items = (ingredient.referenceId ? props.pantry?.[ingredient.referenceId] : undefined);
    result[result.length - 1]!.rows.push({
      // The reference id survives reordering in the editor; the index is the fallback.
      key: ingredient.referenceId ? `ref:${ingredient.referenceId}` : `idx:${index}`,
      ingredient,
      ...lineParts(ingredient),
      status: ingredientStatus(items, today),
      items: items ?? [],
      detail: items?.length ? pantryDetail(items, today, i18n.t, i18n.locale.value) : "",
    });
  });
  return result;
});

/** "4 of 6 in your pantry", over the ingredients that can be told (those naming a food). */
const summary = computed(() => {
  const told = sections.value.flatMap(section => section.rows).filter(row => row.status);
  if (!told.length) {
    return null;
  }
  const missing = told.filter(row => row.status === "missing").map(row => row.ingredient);
  return { have: told.length - missing.length, total: told.length, missing };
});
</script>

<script lang="ts">
/** Session-storage key for cook mode's ingredient ticks of one recipe; cook mode owns them (the recipe page no longer writes them). */
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
  overflow: hidden;
  list-style: none;
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.read-ingredients__item + .read-ingredients__item {
  border-top: 1px solid var(--ds-border);
}

.read-ingredients__row {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  width: 100%;
  padding: calc(var(--ds-space) * 1.25) calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 1.25)
    calc(var(--ds-space) * 1.25);
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
}

.read-ingredients__row--action {
  cursor: pointer;
}

.read-ingredients__row--action:hover {
  background: color-mix(in srgb, var(--ds-text) 4%, transparent);
}

.read-ingredients__bar {
  flex: none;
  align-self: stretch;
  width: 4px;
  min-height: 28px;
  border-radius: 2px;
  background: transparent;
}

.read-ingredients__bar--have {
  background: var(--ds-have);
}

.read-ingredients__bar--missing {
  background: var(--ds-missing);
}

.read-ingredients__bar--soon {
  background: var(--ds-soon-bar);
}

.read-ingredients__body {
  flex: 1;
  min-width: 0;
}

.read-ingredients__label {
  display: block;
  font-size: var(--ds-t-3);
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.read-ingredients__label :deep(sup),
.read-ingredients__label :deep(sub) {
  font-size: 0.7em;
}

.read-ingredients__label :deep(a) {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.read-ingredients__note {
  color: var(--ds-text-2);
}

.read-ingredients__detail {
  display: block;
  margin-top: 2px;
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  line-height: 1.3;
}

.read-ingredients__tag {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px 4px 8px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
}

.read-ingredients__tag--have {
  background: var(--ds-have-surface);
  color: var(--ds-have);
}

.read-ingredients__tag--soon {
  background: var(--ds-soon-surface);
  color: var(--ds-soon);
}

.read-ingredients__tag--missing {
  background: var(--ds-missing-surface);
  color: var(--ds-missing);
}

.read-ingredients__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: calc(var(--ds-space) * 1.5);
  margin: 0 0 calc(var(--ds-space) * 1.5);
  padding: calc(var(--ds-space) * 1.25) calc(var(--ds-space) * 1.5);
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.read-ingredients__summary-text {
  margin: 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
}

.read-ingredients__summary-text strong {
  color: var(--ds-text);
  font-weight: 700;
}

@media (prefers-reduced-motion: reduce) {
  .read-ingredients__chevron {
    transition: none;
  }
}
</style>
