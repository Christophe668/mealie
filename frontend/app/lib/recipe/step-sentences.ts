/*
 * A long step reads better as one bullet per sentence. A sentence ends at ".", "!", "?" or "…" (perhaps
 * followed by a closing bracket or quote), then a space, then a capital letter: "1.5 kg", "env. 3 min",
 * "c. à s." and brackets inside a sentence never split it. A step the author already laid out (line breaks,
 * a list) is left as written.
 */

const SENTENCE_END = /(?<=[.!?…][)\]"»”’]?)\s+(?=["«“(]?\p{Lu})/u;

/** The step's sentences when there are two or more and the step has no layout of its own; otherwise null. */
export function stepSentences(text: string | null | undefined): string[] | null {
  const trimmed = text?.trim();
  if (!trimmed || /\n/u.test(trimmed)) {
    return null;
  }
  const sentences = trimmed.split(SENTENCE_END).map(s => s.trim()).filter(Boolean);
  return sentences.length > 1 ? sentences : null;
}

/** The step as Markdown: a bullet list when it has several sentences, else unchanged. */
export function stepMarkdown(text: string | null | undefined): string {
  const sentences = stepSentences(text);
  return sentences ? sentences.map(s => `- ${s}`).join("\n") : (text ?? "");
}
