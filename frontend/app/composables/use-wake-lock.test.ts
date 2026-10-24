import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent } from "vue";
import { afterEach, describe, expect, test, vi } from "vitest";
import { useWakeLock } from "./use-wake-lock";

const Host = defineComponent({
  setup() {
    useWakeLock();
    return () => null;
  },
});

function fakeWakeLock() {
  const sentinels: { released: boolean; release: ReturnType<typeof vi.fn> }[] = [];
  const request = vi.fn(async () => {
    const sentinel = { released: false, release: vi.fn(async () => { sentinel.released = true; }) };
    sentinels.push(sentinel);
    return sentinel;
  });
  Object.defineProperty(navigator, "wakeLock", { value: { request }, configurable: true });
  return { request, sentinels };
}

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { value: state, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
}

afterEach(() => {
  delete (navigator as { wakeLock?: unknown }).wakeLock;
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
});

describe("useWakeLock", () => {
  test("holds the screen on while mounted and releases on unmount", async () => {
    const { request, sentinels } = fakeWakeLock();
    const wrapper = mount(Host);
    await flushPromises();

    expect(request).toHaveBeenCalledWith("screen");
    wrapper.unmount();
    expect(sentinels[0]!.release).toHaveBeenCalled();
  });

  test("asks again when the page shows after the browser dropped the lock", async () => {
    const { request, sentinels } = fakeWakeLock();
    const wrapper = mount(Host);
    await flushPromises();

    sentinels[0]!.released = true;
    setVisibility("hidden");
    await flushPromises();
    expect(request).toHaveBeenCalledTimes(1);

    setVisibility("visible");
    await flushPromises();
    expect(request).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  test("does nothing while hidden, where unsupported, or when refused", async () => {
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    const { request } = fakeWakeLock();
    mount(Host).unmount();
    expect(request).not.toHaveBeenCalled();

    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    delete (navigator as { wakeLock?: unknown }).wakeLock;
    expect(() => mount(Host).unmount()).not.toThrow();

    Object.defineProperty(navigator, "wakeLock", { value: { request: vi.fn(async () => { throw new Error("NotAllowedError"); }) }, configurable: true });
    const refused = mount(Host);
    await flushPromises();
    refused.unmount();
  });
});
