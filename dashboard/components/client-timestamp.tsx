"use client";

import { useEffect, useState } from "react";

type Props = {
  date: Date | string;
  className?: string;
};

export function ClientTimestamp({ date, className }: Props) {
  const iso = new Date(date).toISOString();
  // Render empty on server, fill in on client to avoid hydration mismatch
  // (server toLocaleString uses server TZ, not the user's browser TZ)
  const [display, setDisplay] = useState("");

  useEffect(() => {
    setDisplay(new Date(iso).toLocaleString());
  }, [iso]);

  return (
    <time dateTime={iso} className={className}>
      {display}
    </time>
  );
}
