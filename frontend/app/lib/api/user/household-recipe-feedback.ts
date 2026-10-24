import { BaseAPI } from "../base/base-clients";
import { route } from "../base/route";
import type { RecipeFeedbackCreate, RecipeFeedbackOut, RecipeFeedbackSummary } from "~/lib/api/types/household";
import type { PaginationData } from "~/lib/api/types/non-generated";

const prefix = "/api";

const routes = {
  feedback: `${prefix}/households/recipe-feedback`,
  feedbackId: (id: string) => `${prefix}/households/recipe-feedback/${id}`,
  summary: `${prefix}/households/recipe-feedback/summary`,
};

/** The household's verdicts on recipes. Recording one also sets last made and adds a timeline entry. */
export class HouseholdRecipeFeedbackApi extends BaseAPI {
  async create(payload: RecipeFeedbackCreate) {
    return await this.requests.post<RecipeFeedbackOut>(routes.feedback, payload);
  }

  /** Newest first; `perPage = -1` returns everything. */
  async list(recipeId: string, page = 1, perPage = -1) {
    return await this.requests.get<PaginationData<RecipeFeedbackOut>>(route(routes.feedback, { recipeId, page, perPage }));
  }

  async remove(id: string) {
    return await this.requests.delete<RecipeFeedbackOut>(routes.feedbackId(id));
  }

  /** Per-recipe summaries keyed by recipe id; recipes without feedback are left out. At most 100 ids. */
  async summaries(recipeIds: string[]) {
    return await this.requests.get<Record<string, RecipeFeedbackSummary>>(
      route(routes.summary, { recipeIds: recipeIds.join(",") }),
    );
  }
}
