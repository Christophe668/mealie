import { BaseCRUDAPI } from "../base/base-clients";
import type {
  AlreadyHaveResult,
  PantryItemCreate,
  PantryItemOut,
  PantryItemUpdate,
  PantryLocation,
  PutAwayResult,
} from "~/lib/api/types/household";

const prefix = "/api";

const routes = {
  pantry: `${prefix}/households/pantry`,
  pantryId: (id: string | number) => `${prefix}/households/pantry/${id}`,
  putAway: (listId: string) => `${prefix}/households/shopping/lists/${listId}/put-away`,
  pantryMatch: (listId: string, itemId: string) =>
    `${prefix}/households/shopping/lists/${listId}/items/${itemId}/pantry-match`,
  alreadyHave: (listId: string, itemId: string) =>
    `${prefix}/households/shopping/lists/${listId}/items/${itemId}/already-have`,
};

export class HouseholdPantryApi extends BaseCRUDAPI<PantryItemCreate, PantryItemOut, PantryItemUpdate> {
  baseRoute = routes.pantry;
  itemRoute = routes.pantryId;

  /**
   * Moves checked items of a shopping list into the pantry; `null` means every checked item.
   * `location` is only sent when given, so the backend default applies otherwise.
   */
  async putAway(listId: string, itemIds: string[] | null, location?: PantryLocation | null) {
    const body = location === undefined ? { itemIds } : { itemIds, location };
    return await this.requests.post<PutAwayResult>(routes.putAway(listId), body);
  }

  /** The pantry row matching a shopping item, or `null` when the pantry holds nothing for it. */
  async pantryMatch(listId: string, itemId: string) {
    return await this.requests.get<PantryItemOut | null>(routes.pantryMatch(listId, itemId));
  }

  /** Removes a shopping item because the household already has it, adding it to the pantry if missing. */
  async alreadyHave(listId: string, itemId: string, location: PantryLocation) {
    return await this.requests.post<AlreadyHaveResult>(routes.alreadyHave(listId, itemId), { location });
  }
}
