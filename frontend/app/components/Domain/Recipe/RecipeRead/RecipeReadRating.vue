<template>
  <div v-if="canRate || average" class="read-rating">
    <div v-if="canRate" class="read-rating__stars" role="group" :aria-label="$t('recipe-read.your-rating')">
      <button
        v-for="n in 5"
        :key="n"
        type="button"
        class="read-rating__star ds-focus"
        :class="{ 'read-rating__star--on': n <= rating }"
        :aria-label="$t('recipe-read.star-label', { n }, n)"
        :aria-pressed="n === rating ? 'true' : 'false'"
        @click="emit('rate', n === rating ? 0 : n)"
      >
        <DsIcon name="star" :size="22" />
      </button>
    </div>
    <p v-else class="read-rating__stars read-rating__stars--static">
      <span class="read-rating__sr">{{ $t("recipe-read.rated", { rating: roundedAverage }) }}</span>
      <DsIcon
        v-for="n in 5"
        :key="n"
        name="star"
        :size="20"
        class="read-rating__star"
        :class="{ 'read-rating__star--on': n <= Math.round(average) }"
      />
    </p>

    <button
      v-if="canRate"
      type="button"
      class="read-rating__favorite ds-focus"
      :aria-pressed="favorite ? 'true' : 'false'"
      :aria-label="$t('recipe-read.favourite')"
      :title="$t('recipe-read.favourite')"
      @click="emit('toggle-favorite')"
    >
      <DsIcon :name="favorite ? 'heart' : 'heartOutline'" :size="22" />
    </button>
  </div>
</template>

<script setup lang="ts">
import DsIcon from "~/components/Design/DsIcon.vue";

const props = withDefaults(defineProps<{
  /** The signed-in user's own rating, 0 = none. */
  rating?: number;
  /** The group's average, shown read-only to visitors. */
  average?: number;
  favorite?: boolean;
  /** Signed in to the recipe's group: rating and favourites are per user. */
  canRate?: boolean;
}>(), {
  rating: 0,
  average: 0,
  favorite: false,
  canRate: false,
});

const emit = defineEmits<{
  (e: "rate", value: number): void;
  (e: "toggle-favorite"): void;
}>();

const roundedAverage = computed(() => Math.round(props.average * 10) / 10);
</script>

<style scoped>
.read-rating {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
}

.read-rating__stars {
  display: inline-flex;
  margin: 0;
}

.read-rating__star {
  display: grid;
  place-items: center;
  padding: 2px;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  /* Off stars stay visible as a control (hairline grey is too faint to read as one). */
  color: color-mix(in srgb, var(--ds-text-2) 45%, transparent);
  cursor: pointer;
}

.read-rating__stars--static .read-rating__star {
  cursor: default;
}

.read-rating__star--on {
  color: var(--ds-text);
}

/* Hover previews the rating in the secondary colour. */
.read-rating__stars:not(.read-rating__stars--static):hover .read-rating__star {
  color: var(--ds-text-2);
}

.read-rating__stars:not(.read-rating__stars--static) .read-rating__star:hover ~ .read-rating__star {
  color: color-mix(in srgb, var(--ds-text-2) 45%, transparent);
}

.read-rating__favorite {
  display: grid;
  place-items: center;
  width: calc(var(--ds-space) * 4.5);
  height: calc(var(--ds-space) * 4.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  cursor: pointer;
}

.read-rating__favorite:hover {
  border-color: var(--ds-text-2);
}

.read-rating__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
