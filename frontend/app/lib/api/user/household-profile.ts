import { BaseAPI } from "../base/base-clients";
import type {
  HouseholdProfileOut,
  MealPreferencesOut,
  MealPreferencesUpdate,
  MemberProfileCreate,
  MemberProfileOut,
  MemberProfileUpdate,
} from "~/lib/api/types/household";

const prefix = "/api";

const routes = {
  profile: `${prefix}/households/profile`,
  members: `${prefix}/households/profile/members`,
  memberId: (id: string) => `${prefix}/households/profile/members/${id}`,
  preferences: `${prefix}/households/profile/preferences`,
};

/** Who eats in the household (diet, allergies, likes) and how it cooks; what Claude follows when planning meals. */
export class HouseholdProfileApi extends BaseAPI {
  async get() {
    return await this.requests.get<HouseholdProfileOut>(routes.profile);
  }

  async createMember(payload: MemberProfileCreate) {
    return await this.requests.post<MemberProfileOut>(routes.members, payload);
  }

  /** Partial: only the fields sent change. */
  async updateMember(id: string, payload: MemberProfileUpdate) {
    return await this.requests.put<MemberProfileOut, MemberProfileUpdate>(routes.memberId(id), payload);
  }

  async deleteMember(id: string) {
    return await this.requests.delete<MemberProfileOut>(routes.memberId(id));
  }

  /** Partial, and creates the household's habits on the first save; null clears a value, [] clears a list. */
  async updatePreferences(payload: MealPreferencesUpdate) {
    return await this.requests.put<MealPreferencesOut, MealPreferencesUpdate>(routes.preferences, payload);
  }
}
