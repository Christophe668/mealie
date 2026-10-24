import { relativeAgo } from "~/composables/use-today";
import type { FeedbackVerdict, RecipeFeedbackOut } from "~/lib/api/types/household";

/** The three answers, in the order cook mode offers them. */
export const FEEDBACK_VERDICTS: readonly FeedbackVerdict[] = ["loved", "ok", "never_again"];

/** Effort levels as the API stores them: 1 easy, 2 fine, 3 a lot of work. */
export const FEEDBACK_EFFORTS: readonly number[] = [1, 2, 3];

export const verdictLabelKey = (verdict: FeedbackVerdict) => `recipe-feedback.verdict.${verdict}`;
export const effortLabelKey = (effort: number) => `recipe-feedback.effort.${effort}`;

type Translate = (key: string, params?: Record<string, unknown>) => string;

/** Newest made first; entries made the same day by most recently recorded. */
export function newestFirst(entries: RecipeFeedbackOut[]): RecipeFeedbackOut[] {
  return [...entries].sort((a, b) =>
    b.madeOn.localeCompare(a.madeOn) || (b.createdAt ?? "").localeCompare(a.createdAt ?? ""),
  );
}

/** "2 weeks ago" or "2 weeks ago, for Sam", starting with a capital ("Yesterday, for Sam"). */
export function feedbackWhenLine(entry: RecipeFeedbackOut, now: Date, t: Translate, locale: string): string {
  const when = relativeAgo(entry.madeOn, now, locale);
  const who = entry.forWhom?.trim();
  const line = who ? t("recipe-feedback.when-for", { when, who }) : when;
  return line.charAt(0).toLocaleUpperCase(locale) + line.slice(1);
}
