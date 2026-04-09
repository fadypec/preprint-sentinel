"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20" role="alert">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
        Something went wrong
      </h2>
      <p className="text-sm text-slate-500 dark:text-slate-400">
        {error.message || "An unexpected error occurred."}
      </p>
      <button
        onClick={reset}
        className="rounded-lg border border-input bg-transparent px-4 py-2 text-sm transition-colors hover:bg-muted dark:bg-input/30 dark:hover:bg-input/50"
      >
        Try again
      </button>
    </div>
  );
}
