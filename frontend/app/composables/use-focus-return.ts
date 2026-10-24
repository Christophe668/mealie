import type { Ref } from "vue";

/**
 * Gives focus back when a dialog opened through v-model (no Vuetify activator) closes: to the element that
 * had focus when it opened, or, when that element is gone by then, to `fallback()`. Without this, Close,
 * Escape and a scrim click all leave keyboard and screen-reader users on <body>.
 */
export function useFocusReturn(open: Ref<boolean>, fallback?: () => HTMLElement | null | undefined) {
  let opener: HTMLElement | null = null;

  // flush: "sync" captures the opener before anything (the dialog's own autofocus) can move focus.
  watch(open, async (isOpen, wasOpen) => {
    if (isOpen && !wasOpen) {
      opener = document.activeElement instanceof HTMLElement && document.activeElement !== document.body
        ? document.activeElement
        : null;
      return;
    }
    if (!isOpen && wasOpen) {
      const target = opener;
      opener = null;
      await nextTick();
      if (target?.isConnected) {
        target.focus();
        return;
      }
      fallback?.()?.focus();
    }
  }, { flush: "sync" });
}
