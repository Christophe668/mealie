import { BaseAPI } from "../base/base-clients";
import { route } from "../base/route";
import type { CookedMealCreate, CookedMealOut, PantryCheckOut, ReadPlanEntry } from "~/lib/api/types/household";

const prefix = "/api";

const routes = {
  cooking: `${prefix}/households/cooking`,
  pantryCheck: (recipeId: string) => `${prefix}/households/cooking/${recipeId}/pantry-check`,
  entryCooked: (entryId: number) => `${prefix}/households/mealplans/${entryId}/cooked`,
};

/** Recording a cooked meal. Dates are the cook's own local day (`YYYY-MM-DD`). */
export class HouseholdCookingApi extends BaseAPI {
  /** The pantry items matching the recipe, the suggested leftover portions and the entry a cooking would mark. */
  async pantryCheck(recipeId: string, cookedOn: string, scale?: number) {
    // `route` stringifies every value, so a missing scale must be left out rather than passed as undefined
    const params = scale === undefined ? { cooked_on: cookedOn } : { cooked_on: cookedOn, scale };
    return await this.requests.get<PantryCheckOut>(route(routes.pantryCheck(recipeId), params));
  }

  async record(payload: CookedMealCreate) {
    return await this.requests.post<CookedMealOut>(routes.cooking, payload);
  }

  /** Ticks a meal plan entry done: a recipe entry is recorded as a cooking, a title-only entry just gets marked. */
  async markCooked(entryId: number, cookedOn: string) {
    return await this.requests.post<CookedMealOut>(route(routes.entryCooked(entryId), { cooked_on: cookedOn }), {});
  }

  async unmarkCooked(entryId: number) {
    return await this.requests.delete<ReadPlanEntry>(routes.entryCooked(entryId));
  }
}
