import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { defineComponent } from "vue";
import type { MemberProfileOut } from "~/lib/api/types/household";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  createMember: vi.fn(),
  updateMember: vi.fn(),
  deleteMember: vi.fn(),
  updatePreferences: vi.fn(),
}));
const toast = vi.hoisted(() => ({ alertUnreportedError: vi.fn() }));

vi.mock("~/composables/api", () => ({ useUserApi: () => ({ householdProfile: api }) }));
vi.mock("~/composables/use-toast", () => toast);

const member = (id: string, name: string): MemberProfileOut => ({ id, name, groupId: "g", householdId: "h" });

/** A load the test answers when it wants to. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(r => (resolve = r));
  return { promise, resolve };
}

async function setup() {
  const { useHouseholdProfile } = await import("~/composables/use-household-profile");
  let result!: ReturnType<typeof useHouseholdProfile>;
  mount(defineComponent({
    setup() {
      result = useHouseholdProfile();
      return () => null;
    },
  }));
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useHouseholdProfile", () => {
  test("a slow load that started first cannot overwrite a newer one", async () => {
    const first = deferred<object>();
    const second = deferred<object>();
    api.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const profile = await setup();

    profile.refresh();
    second.resolve({ data: { members: [member("b", "Bea")], preferences: null } });
    await flushPromises();
    first.resolve({ data: { members: [member("a", "Old")], preferences: null } });
    await flushPromises();

    expect(profile.members.value.map(m => m.name)).toEqual(["Bea"]);
    expect(profile.loading.value).toBe(false);
    expect(profile.loaded.value).toBe(true);
  });

  test("a load that started before a save cannot put the old member back", async () => {
    api.get.mockResolvedValueOnce({ data: { members: [member("s", "Sam")], preferences: null } });
    const profile = await setup();
    await flushPromises();

    const stale = deferred<object>();
    api.get.mockReturnValueOnce(stale.promise);
    profile.refresh();
    api.updateMember.mockResolvedValueOnce({ data: member("s", "Sammy"), error: null });
    await profile.updateMember("s", { name: "Sammy" });

    stale.resolve({ data: { members: [member("s", "Sam")], preferences: null } });
    await flushPromises();

    expect(profile.members.value.map(m => m.name)).toEqual(["Sammy"]);
    expect(profile.loading.value).toBe(false);
  });

  test("a failed save reports it and reloads; create and remove patch the list in place", async () => {
    api.get.mockResolvedValue({ data: { members: [member("s", "Sam")], preferences: null } });
    const profile = await setup();
    await flushPromises();

    const error = { response: { status: 500 } };
    api.updateMember.mockResolvedValueOnce({ data: null, error });
    expect(await profile.updateMember("s", { name: "Sammy" })).toBeNull();
    expect(toast.alertUnreportedError).toHaveBeenCalledExactlyOnceWith(error, "Couldn’t save that change. Try again.");
    expect(api.get).toHaveBeenCalledTimes(2);

    api.createMember.mockResolvedValueOnce({ data: member("k", "Kim"), error: null });
    await profile.createMember({ name: "Kim" });
    api.deleteMember.mockResolvedValueOnce({ data: member("s", "Sam"), error: null });
    expect(await profile.removeMember("s")).toBe(true);

    expect(profile.members.value.map(m => m.name)).toEqual(["Kim"]);
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  test("a failed first load says so and leaves nothing to edit", async () => {
    api.get.mockResolvedValueOnce({ data: null, error: {} });
    const profile = await setup();
    await flushPromises();

    expect(profile.failed.value).toBe(true);
    expect(profile.loaded.value).toBe(false);
  });
});
