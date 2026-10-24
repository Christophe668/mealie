interface Sentinel {
  released: boolean;
  release: () => Promise<void>;
}

/**
 * Keeps the screen on while the calling component is mounted (cook mode). The browser drops the lock
 * whenever the page is hidden, so it is asked for again when the page shows. Silent no-op where the
 * Screen Wake Lock API is missing or refuses.
 */
export function useWakeLock() {
  let sentinel: Sentinel | null = null;
  let active = false;

  function supported() {
    return typeof navigator !== "undefined" && "wakeLock" in navigator && !!navigator.wakeLock;
  }

  async function request() {
    if (!active || !supported() || document.visibilityState !== "visible") {
      return;
    }
    if (sentinel && !sentinel.released) {
      return;
    }
    try {
      const lock = await navigator.wakeLock.request("screen");
      if (!active) {
        await lock.release();
        return;
      }
      sentinel = lock;
    }
    catch {
      // Refused (battery saver, no user activation yet): the screen may dim, cooking still works.
      sentinel = null;
    }
  }

  function onVisibility() {
    void request();
  }

  onMounted(() => {
    active = true;
    document.addEventListener("visibilitychange", onVisibility);
    void request();
  });

  onBeforeUnmount(() => {
    active = false;
    document.removeEventListener("visibilitychange", onVisibility);
    const lock = sentinel;
    sentinel = null;
    if (lock && !lock.released) {
      lock.release().catch(() => {});
    }
  });
}
