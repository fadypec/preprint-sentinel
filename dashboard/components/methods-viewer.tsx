type Props = {
  methods: string | null;
};

export function MethodsViewer({ methods }: Props) {
  if (!methods) {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
        Full text not retrieved. The paper may not have an open-access version, or the methods section could not be extracted.
      </div>
    );
  }

  return (
    <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-4 text-xs leading-relaxed text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
      {methods}
    </pre>
  );
}
