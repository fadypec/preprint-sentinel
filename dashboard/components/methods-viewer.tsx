import React from "react";

type Props = {
  methods: string | null;
  methodsOfConcern?: string[];
};

/**
 * Render methods text with optional highlighting of passages that match
 * key_methods_of_concern from the Stage 4 assessment. Matching is
 * case-insensitive substring search — each concern term highlights all
 * sentences containing it.
 */
export function MethodsViewer({ methods, methodsOfConcern }: Props) {
  if (!methods) {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
        Full text not retrieved. The paper may not have an open-access version, or the methods section could not be extracted.
      </div>
    );
  }

  const highlighted = highlightPassages(methods, methodsOfConcern ?? []);

  return (
    <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-4 text-xs leading-relaxed text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
      {highlighted}
    </pre>
  );
}

/**
 * Split text into sentences and wrap those matching any concern term
 * in a <mark> element with a tooltip showing the matched term.
 */
function highlightPassages(
  text: string,
  concerns: string[],
): (string | React.ReactElement)[] {
  if (concerns.length === 0) return [text];

  // Normalise concern terms for case-insensitive matching
  const lowerConcerns = concerns.map((c) => c.toLowerCase());

  // Split into sentences (rough — split on period+space or newline)
  const sentences = text.split(/(?<=\.)\s+|\n/);
  const result: (string | React.ReactElement)[] = [];

  for (let i = 0; i < sentences.length; i++) {
    const sentence = sentences[i];
    const lowerSentence = sentence.toLowerCase();
    const matchedTerm = lowerConcerns.find((c) => lowerSentence.includes(c));

    if (matchedTerm) {
      // Find the original-case concern for the tooltip
      const originalTerm = concerns[lowerConcerns.indexOf(matchedTerm)];
      result.push(
        <mark
          key={i}
          className="bg-red-100 px-0.5 text-red-900 dark:bg-red-900/30 dark:text-red-200"
          title={`Flagged: ${originalTerm}`}
        >
          {sentence}
        </mark>,
      );
    } else {
      result.push(sentence);
    }

    // Re-add the separator (space or newline) between sentences
    if (i < sentences.length - 1) {
      result.push(" ");
    }
  }

  return result;
}
