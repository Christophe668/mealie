<template>
  <section class="cook-finish" :aria-labelledby="headingId">
    <template v-if="loggedIn">
      <h2 :id="headingId" class="cook-finish__title">
        {{ $t("cook.how-was-it") }}
      </h2>
      <div class="cook-finish__choices">
        <DsButton
          v-for="choice in choices"
          :key="choice.verdict"
          variant="line"
          size="lg"
          :disabled="busy"
          @click="finish(choice.verdict)"
        >
          {{ $t(choice.label) }}
        </DsButton>
        <DsButton variant="ghost" size="lg" class="cook-finish__skip" :disabled="busy" @click="finish(null)">
          {{ $t("cook.skip") }}
        </DsButton>
      </div>
    </template>
    <template v-else>
      <h2 :id="headingId" class="cook-finish__title">
        {{ $t("cook.last-step") }}
      </h2>
      <div class="cook-finish__choices">
        <DsButton variant="line" size="lg" @click="router.push(backTo)">
          {{ $t("cook.done") }}
        </DsButton>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import DsButton from "~/components/Design/DsButton.vue";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";

const props = defineProps<{
  recipeSlug: string;
  /** The recipe page, where every way out leads. */
  backTo: string;
  /** Last made belongs to a household, so visitors get a plain "Done". */
  loggedIn: boolean;
}>();

const headingId = useId();
const router = useRouter();
const i18n = useI18n();

const choices: { verdict: CookVerdict; label: string }[] = [
  { verdict: "loved", label: "cook.loved" },
  { verdict: "fine", label: "cook.fine" },
  { verdict: "not-again", label: "cook.not-again" },
];

const busy = ref(false);

async function finish(verdict: CookVerdict | null) {
  if (busy.value) {
    return;
  }
  busy.value = true;
  if (verdict) {
    try {
      sessionStorage.setItem(pendingFeedbackKey(props.recipeSlug), verdict);
    }
    catch {
      // Private mode: the verdict is lost, last made is still recorded.
    }
  }
  try {
    const { error } = await useUserApi().recipes.updateLastMade(props.recipeSlug, new Date().toISOString());
    if (error) {
      alert.error(i18n.t("cook.save-failed"));
    }
  }
  catch {
    alert.error(i18n.t("cook.save-failed"));
  }
  busy.value = false;
  router.push(props.backTo);
}
</script>

<script lang="ts">
export type CookVerdict = "loved" | "fine" | "not-again";

/** Where phase 2's household feedback picks the verdict up. */
export function pendingFeedbackKey(slug: string) {
  return `pending-feedback:${slug}`;
}
</script>

<style scoped>
.cook-finish {
  padding-top: calc(var(--ds-space) * 4);
  border-top: 1px solid var(--ds-border);
}

.cook-finish__title {
  margin: 0 0 calc(var(--ds-space) * 2);
  font-size: var(--ds-t-5);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.02em;
  line-height: 1.15;
}

/* Skip is the quiet way out: no outline next to the three answers. */
.cook-finish__choices :deep(.cook-finish__skip) {
  border-color: transparent;
  color: var(--ds-text-2);
}

.cook-finish__choices {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
}

@media (max-width: 1023px) {
  .cook-finish__choices {
    flex-direction: column;
  }

  .cook-finish__choices :deep(.ds-btn) {
    width: 100%;
  }
}
</style>
