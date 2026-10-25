import { describe, expect, test } from "vitest";
import { parseThermomix } from "./thermomix";

describe("parseThermomix", () => {
  test("reads a Cookomix step, bold and all, and takes the settings out of the text", () => {
    const step = parseThermomix("Mettre le lait et la semoule dans le bol. Cuire **15 min**/**100°C**//**vitesse 1** sans le gobelet doseur.");

    expect(step?.programs).toEqual([{ time: "15 min", temperature: "100°C", speed: "1", reverse: false, turbo: false, dough: false }]);
    expect(step?.text).toBe("Mettre le lait et la semoule dans le bol. Cuire sans le gobelet doseur.");
  });

  test("time with seconds, speed only, ranges and reverse", () => {
    expect(parseThermomix("Chauffer 5 min 30 sec/80°C/vitesse 1.")?.programs[0]).toMatchObject({ time: "5 min 30 sec", temperature: "80°C", speed: "1" });
    expect(parseThermomix("Pulvériser 15 sec/vitesse 10.")).toEqual({
      programs: [{ time: "15 sec", temperature: null, speed: "10", reverse: false, turbo: false, dough: false }],
      text: "Pulvériser.",
    });
    expect(parseThermomix("Mixer 30 sec / vitesse 5-10 progressivement.")?.programs[0]?.speed).toBe("5–10");
    expect(parseThermomix("Cuire 20 min / 100°C / ⟲ / vitesse 1.")?.programs[0]).toMatchObject({ reverse: true, speed: "1" });
    expect(parseThermomix("Mijoter 25 min/90°C/sens inverse/vitesse mijotage.")?.programs[0]).toMatchObject({ reverse: true, speed: "spoon" });
  });

  test("Varoma, Turbo and the dough mode", () => {
    expect(parseThermomix("Cuire 20 min/Varoma/vitesse 1.")?.programs[0]?.temperature).toBe("Varoma");
    expect(parseThermomix("Hacher 3 sec/Turbo.")?.programs[0]).toMatchObject({ time: "3 sec", turbo: true, speed: null });
    expect(parseThermomix("Pétrir 2 min/mode pétrin.")?.programs[0]).toMatchObject({ time: "2 min", dough: true });
  });

  test("English and comma separators", () => {
    expect(parseThermomix("Cook 10 min, 100°C, speed 2, reverse.")?.programs[0]).toMatchObject({ time: "10 min", temperature: "100°C", speed: "2", reverse: true });
  });

  test("two programs in one step", () => {
    const step = parseThermomix("Mixer 10 sec/vitesse 5, puis cuire 3 min/100°C/vitesse 1.");

    expect(step?.programs.map(p => p.speed)).toEqual(["5", "1"]);
    expect(step?.text).toBe("Mixer, puis cuire.");
  });

  test("ordinary steps stay ordinary", () => {
    expect(parseThermomix("Préchauffer le four à 180°C.")).toBeNull();
    expect(parseThermomix("Réserver au frigo pendant 4 h.")).toBeNull();
    expect(parseThermomix("Fry the onions for 10 min.")).toBeNull();
    expect(parseThermomix("")).toBeNull();
    expect(parseThermomix(null)).toBeNull();
  });
});
