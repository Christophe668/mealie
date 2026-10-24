import type { MaybeRefOrGetter } from "vue";

/**
 * Title shown in the app shell's top bar.
 *
 * Pages call `useAppShellTitle(() => t("..."))` in setup; the shell calls `useAppShellTitle()` to read it.
 * Titles are stored per route path, so a page that never sets one shows an empty title instead of
 * inheriting the previous page's.
 */
export function useAppShellTitle(title?: MaybeRefOrGetter<string>) {
  const titles = useState<Record<string, string>>("app-shell-titles", () => ({}));
  const route = useRoute();

  if (title !== undefined) {
    // Captured once: a page instance belongs to the path it was created for.
    const path = route.path;
    watchEffect(() => {
      titles.value[path] = toValue(title);
    });
  }

  return computed(() => titles.value[route.path] ?? "");
}
