import type { Ref } from "vue";

const clone = <V>(value: V): V => JSON.parse(JSON.stringify(value));
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/**
 * A form's draft of `source()` that keeps what the user typed and still follows the source.
 *
 * Each field remembers the value it started from (the snapshot). A field is touched while its draft differs
 * from that snapshot. When the source changes (a reload, or Claude editing the same record), every untouched
 * field takes the new value and its snapshot moves with it, while touched fields keep what was typed. `changes`
 * holds only the touched fields, so a save never sends back a stale value of a field the user left alone.
 *
 * `normalise` turns the draft into what is sent (trimmed text, empty notes as null); fields are compared in
 * that form, so typing a trailing space is not a change.
 */
export function useTrackedDraft<T extends object, N extends Record<keyof T, unknown>>(
  source: () => T,
  normalise: (value: T) => N,
) {
  const snapshot = ref(clone(source())) as Ref<T>;
  const draft = ref(clone(source())) as Ref<T>;

  const changes = computed(() => {
    const now = normalise(draft.value);
    const base = normalise(snapshot.value);
    const result: Partial<N> = {};
    for (const key of Object.keys(now) as (keyof T)[]) {
      if (!same(now[key], base[key])) {
        result[key] = now[key];
      }
    }
    return result;
  });

  /**
   * Takes `next` into every untouched field. Fields in `sent` were just saved: their snapshot moves to `next`,
   * and so does their draft unless it was edited again while the save ran.
   */
  function rebase(next: T, sent: Partial<N> = {}) {
    const fresh = clone(next);
    const now = normalise(draft.value);
    for (const key of Object.keys(fresh) as (keyof T)[]) {
      if (key in sent) {
        if (same(now[key], sent[key])) {
          draft.value[key] = fresh[key];
        }
        snapshot.value[key] = fresh[key];
      }
      else if (same(draft.value[key], snapshot.value[key])) {
        draft.value[key] = fresh[key];
        snapshot.value[key] = fresh[key];
      }
    }
  }

  watch(source, next => rebase(next));

  return {
    draft,
    changes,
    /** After a successful save, once the source shows the saved record: `sent` is what the save sent. */
    commit: (sent: Partial<N>) => rebase(source(), sent),
  };
}
