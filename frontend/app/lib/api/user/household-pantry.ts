import { BaseCRUDAPI } from "../base/base-clients";
import type { PantryItemCreate, PantryItemOut, PantryItemUpdate, PutAwayResult } from "~/lib/api/types/household";

const prefix = "/api";

const routes = {
  pantry: `${prefix}/households/pantry`,
  pantryId: (id: string | number) => `${prefix}/households/pantry/${id}`,
  putAway: (listId: string) => `${prefix}/households/shopping/lists/${listId}/put-away`,
};

export class HouseholdPantryApi extends BaseCRUDAPI<PantryItemCreate, PantryItemOut, PantryItemUpdate> {
  baseRoute = routes.pantry;
  itemRoute = routes.pantryId;

  /** Moves checked items of a shopping list into the pantry; `null` means every checked item. */
  async putAway(listId: string, itemIds: string[] | null) {
    return await this.requests.post<PutAwayResult>(routes.putAway(listId), { itemIds });
  }
}
