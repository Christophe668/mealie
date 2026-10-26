<template>
  <!-- v-theme--light pins the light token values inside the board: saffron always carries ink, so the
       dark button stays ink and the ghost button's border stays ink-tinted in dark mode too. -->
  <section
    class="home-board v-theme--light"
    :class="{ 'home-board--enter': animate }"
    :aria-busy="loading ? 'true' : undefined"
    :aria-labelledby="loading ? undefined : titleId"
  >
    <div class="home-board__photo" :class="{ 'home-board__photo--empty': !loading && (!imageUrl || imageFailed) }">
      <img
        v-if="imageUrl && !imageFailed"
        :src="imageUrl"
        alt=""
        @error="imageFailed = true"
      >
      <DsIcon v-else-if="!loading" name="silverwareForkKnife" :size="40" class="home-board__placeholder-icon" />
    </div>

    <div class="home-board__body">
      <p class="home-board__label">
        {{ $t("home-today.tonight") }}
      </p>

      <template v-if="loading">
        <span class="home-board__skeleton ds-display" aria-hidden="true" />
        <span class="home-board__skeleton home-board__skeleton--short ds-display" aria-hidden="true" />
      </template>

      <template v-else-if="entry">
        <h2 :id="titleId" class="home-board__title ds-display">
          {{ title }}
        </h2>
        <p v-if="timeLine" class="home-board__fact">
          {{ timeLine }}
        </p>
        <p v-if="lastMadeLine" class="home-board__fact">
          {{ lastMadeLine }}
        </p>
        <div class="home-board__actions">
          <DsButton v-if="cookTo && !cooked" variant="dark" :to="cookTo">
            {{ $t("home-today.start-cooking") }}
          </DsButton>
          <DsButton v-if="finishTo" :variant="cooked ? 'dark' : 'ghost'" :to="finishTo">
            {{ $t("cook.how-was-it") }}
          </DsButton>
          <DsButton variant="ghost" icon="swapHorizontal" @click="emit('swap')">
            {{ $t("home-today.swap") }}
          </DsButton>
        </div>
      </template>

      <template v-else>
        <h2 :id="titleId" class="home-board__title ds-display">
          {{ $t("home-today.nothing-planned-tonight") }}
        </h2>
        <div class="home-board__actions">
          <DsButton variant="dark" :to="finderTo">
            {{ $t("home-today.pick-a-recipe") }}
          </DsButton>
          <DsButton variant="ghost" :to="plannerTo">
            {{ $t("home-today.plan-the-week") }}
          </DsButton>
        </div>
        <p v-if="hasConnection === false" class="home-board__aside">
          <NuxtLink to="/user/connections" class="home-board__link ds-focus">
            {{ $t("home-today.or-ask-claude") }}
          </NuxtLink>
        </p>
        <p v-else-if="hasConnection === true" class="home-board__aside">
          {{ $t("home-today.or-ask-claude") }}
        </p>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import DsButton from "~/components/Design/DsButton.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { useStaticRoutes } from "~/composables/api";
import { howWasItTo, useTodayFormat } from "~/composables/use-today";
import type { ReadPlanEntry } from "~/lib/api/types/meal-plan";

const props = withDefaults(defineProps<{
  entry: ReadPlanEntry | null;
  loading: boolean;
  groupSlug: string;
  /** null = unknown (lookup failed); undefined = not looked up. */
  lastMade?: string | null;
  /** Whether an MCP client is connected; null when unknown, which hides the "ask Claude" line. */
  hasConnection?: boolean | null;
  plannerTo: string;
  today: Date;
}>(), {
  lastMade: undefined,
  hasConnection: null,
});

const emit = defineEmits<{ (e: "swap"): void }>();

// The entrance plays once per page load, not on every return to Home.
const animate = !entrancePlayed;
entrancePlayed = true;

const titleId = useId();
const { recipeImage } = useStaticRoutes();
const { timeAndServings, lastMadeLabel } = useTodayFormat();

const recipe = computed(() => props.entry?.recipe ?? null);
const title = computed(() => recipe.value?.name || props.entry?.title || "");
const timeLine = computed(() => timeAndServings(recipe.value, props.entry?.recipeScale ?? 1));
// "Never cooked" is a shelf label; on the board an unknown or empty history simply says nothing.
const lastMadeLine = computed(() => (props.lastMade ? lastMadeLabel(props.lastMade, props.today) : ""));

const imageFailed = ref(false);
const imageUrl = computed(() => (recipe.value?.id && recipe.value.image ? recipeImage(recipe.value.id, recipe.value.image) : ""));
watch(imageUrl, () => (imageFailed.value = false));

const cookTo = computed(() => (recipe.value?.slug ? `/g/${props.groupSlug}/r/${recipe.value.slug}/cook` : ""));
// Told later: after eating, or once it was ticked done. Once cooked it is the board's main action.
const cooked = computed(() => !!props.entry?.cookedAt);
const finishTo = computed(() => (props.entry ? howWasItTo(props.groupSlug, props.entry, props.today) : ""));
const finderTo = computed(() => `/g/${props.groupSlug}/recipes/finder`);
</script>

<script lang="ts">
let entrancePlayed = false;
</script>

<style scoped>
.home-board {
  display: grid;
  grid-template-columns: minmax(160px, 200px) minmax(0, 1fr);
  gap: calc(var(--ds-space) * 3);
  padding: calc(var(--ds-space) * 3);
  border-radius: var(--ds-radius-hero);
  background: var(--ds-accent);
  color: var(--ds-accent-text);
}

.home-board--enter {
  animation: home-board-rise 320ms cubic-bezier(0.2, 0.7, 0.2, 1) both;
}

@keyframes home-board-rise {
  from {
    opacity: 0;
    transform: translateY(12px);
  }

  to {
    opacity: 1;
    transform: none;
  }
}

.home-board__photo {
  display: grid;
  place-items: center;
  align-self: start;
  aspect-ratio: 1 / 1;
  overflow: hidden;
  border-radius: calc(var(--ds-radius-hero) - var(--ds-space));
  background: color-mix(in srgb, var(--ds-accent-text) 10%, transparent);
}

.home-board__photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.home-board__placeholder-icon {
  opacity: 0.45;
}

.home-board__body {
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
}

.home-board__label {
  margin: 0 0 calc(var(--ds-space) * 0.75);
  font-size: var(--ds-t-2);
  font-weight: 600;
}

.home-board__title {
  display: -webkit-box;
  margin: 0 0 calc(var(--ds-space) * 1.25);
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  overflow-wrap: anywhere;
}

.home-board__fact {
  margin: 0;
  font-size: var(--ds-t-2);
}

.home-board__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
  margin-top: calc(var(--ds-space) * 2.25);
}

.home-board__aside {
  margin: calc(var(--ds-space) * 1.5) 0 0;
  font-size: var(--ds-t-2);
}

.home-board__link {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.home-board__skeleton {
  display: block;
  width: min(100%, 7em);
  height: 0.9em;
  margin-bottom: calc(var(--ds-space) * 1.25);
  border-radius: var(--ds-radius-ctl);
  background: color-mix(in srgb, var(--ds-accent-text) 12%, transparent);
}

.home-board__skeleton--short {
  width: min(70%, 4.5em);
}

@media (max-width: 1023px) {
  /* Full-bleed on mobile: cancel the shell's 16 px gutter. */
  .home-board {
    grid-template-columns: minmax(0, 1fr);
    gap: calc(var(--ds-space) * 2);
    margin-inline: calc(var(--ds-space) * -2);
    padding: calc(var(--ds-space) * 2.5) calc(var(--ds-space) * 2);
    border-radius: 0;
  }

  .home-board__photo {
    aspect-ratio: 3 / 2;
    align-self: stretch;
  }

  .home-board__title {
    font-size: var(--ds-t-6);
  }

  /* Without a photo, a blank block only pushes the actions below the fold. */
  .home-board__photo--empty {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .home-board--enter {
    animation: none;
  }
}
</style>
