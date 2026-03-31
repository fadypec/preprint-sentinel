"use client";

import { useState, useTransition } from "react";
import { ReviewStatus } from "@prisma/client";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const statusLabels: Record<ReviewStatus, string> = {
  [ReviewStatus.unreviewed]: "Unreviewed",
  [ReviewStatus.under_review]: "Under Review",
  [ReviewStatus.confirmed_concern]: "Confirmed Concern",
  [ReviewStatus.false_positive]: "False Positive",
  [ReviewStatus.archived]: "Archived",
};

type Props = {
  paperId: string;
  currentStatus: ReviewStatus;
};

export function ReviewStatusSelect({ paperId, currentStatus }: Props) {
  const [status, setStatus] = useState<ReviewStatus>(currentStatus);
  const [isPending, startTransition] = useTransition();

  function handleChange(value: ReviewStatus | null) {
    if (!value) return;
    setStatus(value);
    startTransition(async () => {
      await fetch(`/api/papers/${paperId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewStatus: value }),
      });
    });
  }

  return (
    <Select value={status} onValueChange={handleChange} disabled={isPending}>
      <SelectTrigger aria-label="Change review status">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {Object.entries(statusLabels).map(([value, label]) => (
          <SelectItem key={value} value={value}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
