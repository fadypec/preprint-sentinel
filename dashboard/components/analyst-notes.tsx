"use client";

import { useState, useTransition } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Save } from "lucide-react";

type Props = {
  paperId: string;
  initialNotes: string | null;
};

export function AnalystNotes({ paperId, initialNotes }: Props) {
  const [notes, setNotes] = useState(initialNotes ?? "");
  const [isPending, startTransition] = useTransition();
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function save() {
    startTransition(async () => {
      const response = await fetch(`/api/papers/${paperId}/notes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes }),
      });
      if (response.ok) {
        setError(null);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      } else {
        setError("Failed to save notes");
      }
    });
  }

  return (
    <div>
      <label htmlFor="analyst-notes-textarea" className="sr-only">Analyst notes</label>
      <Textarea
        id="analyst-notes-textarea"
        value={notes}
        onChange={(e) => { setNotes(e.target.value); setSaved(false); setError(null); }}
        placeholder="Add analyst notes..."
        rows={4}
        aria-label="Analyst notes"
      />
      <div className="mt-2 flex items-center gap-2">
        <Button size="sm" onClick={save} disabled={isPending}>
          <Save className="mr-1 h-3 w-3" />
          {isPending ? "Saving..." : "Save"}
        </Button>
        {saved && (
          <span className="text-xs text-green-600 dark:text-green-400" aria-live="polite">
            Saved
          </span>
        )}
        {error && (
          <span className="text-xs text-red-600 dark:text-red-400" aria-live="polite">
            {error}
          </span>
        )}
      </div>
    </div>
  );
}
