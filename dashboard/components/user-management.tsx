"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type User = {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
  role: string;
  status: string;
  createdAt: string;
};

export function UserManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/users")
      .then((r) => r.json())
      .then((data) => {
        setUsers(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  async function updateStatus(userId: string, status: string) {
    setUpdating(userId);
    try {
      const resp = await fetch("/api/users", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userId, status }),
      });
      if (resp.ok) {
        const updated = await resp.json();
        setUsers((prev) =>
          prev.map((u) => (u.id === updated.id ? { ...u, status: updated.status } : u)),
        );
      }
    } finally {
      setUpdating(null);
    }
  }

  if (loading) {
    return <div className="h-20 motion-safe:animate-pulse rounded bg-slate-200 dark:bg-slate-700" />;
  }

  const pending = users.filter((u) => u.status === "pending");
  const others = users.filter((u) => u.status !== "pending");

  return (
    <div className="space-y-4">
      {pending.length > 0 && (
        <div className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
          <strong>{pending.length}</strong> user{pending.length !== 1 ? "s" : ""} awaiting approval
        </div>
      )}

      <div className="space-y-2">
        {[...pending, ...others].map((user) => (
          <div
            key={user.id}
            className={cn(
              "flex items-center justify-between rounded-md border p-3",
              user.status === "pending"
                ? "border-amber-300 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-900/10"
                : "border-slate-200 dark:border-slate-700",
            )}
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                  {user.name || user.email}
                </span>
                <Badge
                  variant="outline"
                  className={cn(
                    "text-[10px]",
                    user.status === "approved" && "border-green-300 text-green-700 dark:border-green-700 dark:text-green-400",
                    user.status === "pending" && "border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-400",
                    user.status === "rejected" && "border-red-300 text-red-700 dark:border-red-700 dark:text-red-400",
                  )}
                >
                  {user.status}
                </Badge>
                <Badge variant="outline" className="text-[10px]">
                  {user.role}
                </Badge>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {user.email} &middot; joined {new Date(user.createdAt).toLocaleDateString()}
              </p>
            </div>

            <div className="flex gap-1.5">
              {user.status !== "approved" && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={updating === user.id}
                  onClick={() => updateStatus(user.id, "approved")}
                  className="h-7 text-xs text-green-700 hover:bg-green-50 dark:text-green-400"
                  aria-label={`Approve ${user.name || user.email}`}
                >
                  Approve
                </Button>
              )}
              {user.status !== "rejected" && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={updating === user.id}
                  onClick={() => updateStatus(user.id, "rejected")}
                  className="h-7 text-xs text-red-700 hover:bg-red-50 dark:text-red-400"
                  aria-label={`Reject ${user.name || user.email}`}
                >
                  Reject
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
