import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, test, vi } from "vitest";
import ProfileMemberCard from "./ProfileMemberCard.vue";
import type { MemberProfileOut } from "~/lib/api/types/household";

const stubs = { "v-icon": { template: "<i />" } };

const sam: MemberProfileOut = {
  id: "sam",
  groupId: "g",
  householdId: "h",
  name: "Sam",
  isChild: true,
  diet: "none",
  allergies: ["peanuts"],
  exclusions: [],
  dislikes: ["olives"],
  likes: [],
  notes: null,
};

function render(saveMember: (data: object) => Promise<boolean>, member: Partial<MemberProfileOut> = sam, isYou = false) {
  return mount(ProfileMemberCard, { props: { member, saveMember, isYou }, global: { stubs } });
}

const saveButton = (wrapper: ReturnType<typeof render>) => wrapper.find("button[type=submit]");

describe("ProfileMemberCard", () => {
  test("Save stays disabled until something changes, and again when the change is undone", async () => {
    const save = vi.fn().mockResolvedValue(true);
    const wrapper = render(save);

    expect(saveButton(wrapper).attributes("aria-disabled")).toBe("true");
    await wrapper.find("form").trigger("submit");
    expect(save).not.toHaveBeenCalled();

    await wrapper.find("select").setValue("vegetarian");
    expect(saveButton(wrapper).attributes("aria-disabled")).toBeUndefined();

    await wrapper.find("select").setValue("none");
    expect(saveButton(wrapper).attributes("aria-disabled")).toBe("true");
  });

  test("saves only the changed fields, then shows the saved member as clean", async () => {
    const save = vi.fn().mockImplementation(async (data) => {
      await wrapper.setProps({ member: { ...sam, ...data } });
      return true;
    });
    const wrapper = render(save);

    await wrapper.find("input[type=checkbox]").setValue(false);
    const notes = wrapper.find("textarea");
    await notes.setValue("  Eats early  ");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(save).toHaveBeenCalledExactlyOnceWith({ isChild: false, notes: "Eats early" });
    expect(saveButton(wrapper).attributes("aria-disabled")).toBe("true");
    expect((notes.element as HTMLTextAreaElement).value).toBe("Eats early");
  });

  test("a failed save keeps what was typed and Save stays available", async () => {
    let finish!: (ok: boolean) => void;
    const save = vi.fn(() => new Promise<boolean>(resolve => (finish = resolve)));
    const wrapper = render(save);

    await wrapper.find("input[type=text]").setValue("Samantha");
    await wrapper.find("form").trigger("submit");
    // busy while saving: a second submit is ignored
    expect(saveButton(wrapper).attributes("aria-disabled")).toBe("true");
    await wrapper.find("form").trigger("submit");
    expect(save).toHaveBeenCalledOnce();

    finish(false);
    await flushPromises();

    expect((wrapper.find("input[type=text]").element as HTMLInputElement).value).toBe("Samantha");
    expect(saveButton(wrapper).attributes("aria-disabled")).toBeUndefined();
  });

  test("a reload keeps what was typed but updates an untouched card", async () => {
    const wrapper = render(vi.fn());

    await wrapper.setProps({ member: { ...sam, dislikes: ["olives", "mushrooms"] } });
    expect(wrapper.findAll("li").map(li => li.text())).toContain("mushrooms");

    await wrapper.find("input[type=text]").setValue("Sammy");
    await wrapper.setProps({ member: { ...sam, name: "Samuel" } });
    expect((wrapper.find("input[type=text]").element as HTMLInputElement).value).toBe("Sammy");
  });

  test("allergies are the only saffron chips; the You badge shows for the signed-in user", () => {
    const wrapper = render(vi.fn(), sam, true);

    const accent = wrapper.findAll(".ds-chip--accent");
    expect(accent.map(chip => chip.text())).toEqual(["peanuts"]);
    expect(wrapper.text()).toContain("You");
    expect(render(vi.fn()).text()).not.toContain("You");
  });

  test("a new card can be saved as soon as it has a name and sends everything", async () => {
    const save = vi.fn().mockResolvedValue(true);
    const wrapper = render(save, {});

    expect(saveButton(wrapper).attributes("aria-disabled")).toBe("true");
    await wrapper.find("input[type=text]").setValue(" Kim ");
    await wrapper.find("form").trigger("submit");

    expect(save).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ name: "Kim", diet: "none", allergies: [], notes: null }));
  });

  test("Remove asks the page", async () => {
    const wrapper = render(vi.fn());
    await wrapper.findAll("button").find(b => b.text() === "Remove")!.trigger("click");
    expect(wrapper.emitted("remove")).toHaveLength(1);
  });
});
