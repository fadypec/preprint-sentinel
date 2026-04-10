"use client";

type Props = {
  date: Date | string;
  className?: string;
};

export function ClientTimestamp({ date, className }: Props) {
  const iso = new Date(date).toISOString();

  return (
    <time dateTime={iso} className={className} suppressHydrationWarning>
      {new Date(iso).toLocaleString()}
    </time>
  );
}
