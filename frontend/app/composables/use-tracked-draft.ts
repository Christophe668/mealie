import type { Ref } from "vue";

const clone = <V>(value: V): V => JSON.parse(JSON.stringify(value));
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/**
 * A form's draft of `source()` that keeps what the user typed and still follows the source.
 *
 * Each field remembers the value the user started editing from (its origin). A field is touched while its draft
 * differs from that origin. Fields are compared in `normalise`d form (trimmed text, empty notes as null), so a
 * trailing space is not an edit.
 *
 * - When the source changes (a reload, or Claude editing the same record), every untouched field takes the new
 *   value, while touched fields keep what was typed.
 * - When the user undoes an edit back to the origin, the field is untouched again and takes the current source
 *   value, which may have moved on in the meantime.
 * - A touched field whose draft equals the current source is untouched again: there is nothing left to send.
 *
 * `changes` holds only the touched fields that differ from the current source, so a save never sends back a stale
 * value of a field the user left alone.
 */
export function useTrackedDraft<T extends object, N extends Record<keyof T, unknown>>(
  source: () => T,
  normalise: (value: T) => N,
) {
  /** The latest source. */
  const base = ref(clone(source())) as Ref<T>;
  /** Per field, the value the draft started from. Equal to `base` for untouched fields once settled. */
  const origin = ref(clone(source())) as Ref<T>;
  const draft = ref(clone(source())) as Ref<T>;

  const changes = computed(() => {
    const now = normalise(draft.value);
    const from = normalise(origin.value);
    const latest = normalise(base.value);
    const result: Partial<N> = {};
    for (const key of Object.keys(now) as (keyof T)[]) {
      if (!same(now[key], from[key]) && !same(now[key], latest[key])) {
        result[key] = now[key];
      }
    }
    return result;
  });

  /** Brings untouched fields up to the latest source. Assigns only on a difference, so it is idempotent. */
  function settle() {
    const now = normalise(draft.value);
    const from = normalise(origin.value);
    const latest = normalise(base.value);
    for (const key of Object.keys(base.value) as (keyof T)[]) {
      if (same(now[key], latest[key])) {
        // Typed exactly what the source holds (or never left it): keep the text, follow the source from here.
        if (!same(origin.value[key], base.value[key])) {
          origin.value[key] = clone(base.value[key]);
        }
      }
      else if (same(now[key], from[key])) {
        // Untouched (possibly after an undo) but behind the source: take the source value.
        draft.value[key] = clone(base.value[key]);
        origin.value[key] = clone(base.value[key]);
      }
    }
  }

  /**
   * Takes `next` as the source. Fields in `sent` were just saved: their origin moves to `next`, and so does their
   * draft unless it was edited again while the save ran.
   */
  function rebase(next: T, sent: Partial<N> = {}) {
    const fresh = clone(next);
    const now = normalise(draft.value);
    for (const key of Object.keys(sent) as (keyof T)[]) {
      if (key in fresh) {
        if (same(now[key], sent[key])) {
          draft.value[key] = clone(fresh[key]);
        }
        origin.value[key] = clone(fresh[key]);
      }
    }
    base.value = fresh;
    settle();
  }

  watch(source, next => rebase(next));
  watch(draft, settle, { deep: true });

  return {
    draft,
    changes,
    /** After a successful save, once the source shows the saved record: `sent` is what the save sent. */
    commit: (sent: Partial<N>) => rebase(source(), sent),
  };
}
