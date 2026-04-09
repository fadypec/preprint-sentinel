"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Card } from "@/components/ui/card";
import { Save } from "lucide-react";

type SettingsData = {
  stage1_model: string;
  stage2_model: string;
  stage3_model: string;
  coarse_filter_threshold: number;
  adjudication_min_tier: string;
  use_batch_api: boolean;
  pubmed_query_mode: string;
  biorxiv_request_delay: number;
  pubmed_request_delay: number;
  europepmc_request_delay: number;
  unpaywall_request_delay: number;
  openalex_request_delay: number;
  semantic_scholar_request_delay: number;
  orcid_request_delay: number;
  fulltext_request_delay: number;
  alert_email_recipients: string;
  alert_slack_webhook: string;
  alert_digest_frequency: string;
  alert_tier_threshold: string;
};

const DEFAULTS: SettingsData = {
  stage1_model: "claude-haiku-4-5-20251001",
  stage2_model: "claude-sonnet-4-6",
  stage3_model: "claude-opus-4-6",
  coarse_filter_threshold: 0.8,
  adjudication_min_tier: "high",
  use_batch_api: false,
  pubmed_query_mode: "mesh_filtered",
  biorxiv_request_delay: 1.0,
  pubmed_request_delay: 0.1,
  europepmc_request_delay: 1.0,
  unpaywall_request_delay: 0.1,
  openalex_request_delay: 0.1,
  semantic_scholar_request_delay: 1.0,
  orcid_request_delay: 1.0,
  fulltext_request_delay: 1.0,
  alert_email_recipients: "",
  alert_slack_webhook: "",
  alert_digest_frequency: "daily",
  alert_tier_threshold: "high",
};

type Props = {
  initialSettings: Partial<SettingsData>;
};

export function SettingsForm({ initialSettings }: Props) {
  const [settings, setSettings] = useState<SettingsData>({
    ...DEFAULTS,
    ...initialSettings,
  });
  const [isPending, startTransition] = useTransition();
  const [saved, setSaved] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  function update<K extends keyof SettingsData>(key: K, value: SettingsData[K]) {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  async function testAlert(channel: "slack" | "email") {
    setTestResult(null);
    const res = await fetch("/api/alerts/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel }),
    });
    const data = await res.json();
    setTestResult(
      data.ok
        ? `${channel} test sent!`
        : `${channel} failed: ${data.error}`,
    );
    setTimeout(() => setTestResult(null), 5000);
  }

  function save() {
    startTransition(async () => {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    });
  }

  return (
    <div className="space-y-6">
      {/* Model Selection */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Model Selection
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {(["stage1_model", "stage2_model", "stage3_model"] as const).map(
            (key) => (
              <div key={key}>
                <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
                  {key === "stage1_model"
                    ? "Stage 1 (Coarse)"
                    : key === "stage2_model"
                      ? "Stage 2 (Methods)"
                      : "Stage 3 (Adjudication)"}
                </label>
                <Input
                  value={settings[key]}
                  onChange={(e) => update(key, e.target.value)}
                />
              </div>
            ),
          )}
        </div>
      </Card>

      {/* Pipeline Tuning */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Pipeline Tuning
        </h2>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
              Coarse Filter Threshold:{" "}
              {settings.coarse_filter_threshold.toFixed(2)}
            </label>
            <Slider
              value={[settings.coarse_filter_threshold]}
              onValueChange={(v) => {
                const arr = v as number[];
                update("coarse_filter_threshold", arr[0]);
              }}
              min={0}
              max={1}
              step={0.05}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
              Adjudication Min Tier
            </label>
            <Select
              value={settings.adjudication_min_tier}
              onValueChange={(v) => {
                if (v != null) update("adjudication_min_tier", v);
              }}
            >
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-3">
            <Switch
              checked={settings.use_batch_api}
              onCheckedChange={(v) => update("use_batch_api", v)}
              id="batch-api"
            />
            <label
              htmlFor="batch-api"
              className="text-xs text-slate-700 dark:text-slate-300"
            >
              Use Batch API
            </label>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
              PubMed Query Mode
            </label>
            <Select
              value={settings.pubmed_query_mode}
              onValueChange={(v) => {
                if (v != null) update("pubmed_query_mode", v);
              }}
            >
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="mesh_filtered">MeSH Filtered</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </Card>

      {/* Rate Limits */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Rate Limits (seconds)
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {(
            [
              ["biorxiv_request_delay", "bioRxiv"],
              ["pubmed_request_delay", "PubMed"],
              ["europepmc_request_delay", "Europe PMC"],
              ["unpaywall_request_delay", "Unpaywall"],
              ["openalex_request_delay", "OpenAlex"],
              ["semantic_scholar_request_delay", "Semantic Scholar"],
              ["orcid_request_delay", "ORCID"],
              ["fulltext_request_delay", "Full-text"],
            ] as const
          ).map(([key, label]) => (
            <div key={key}>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
                {label}
              </label>
              <Input
                type="number"
                step={0.1}
                min={0}
                value={settings[key]}
                onChange={(e) => update(key, parseFloat(e.target.value) || 0)}
              />
            </div>
          ))}
        </div>
      </Card>

      {/* Alerts */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Alerts
        </h2>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
              Email Recipients (comma-separated)
            </label>
            <Input
              value={settings.alert_email_recipients}
              onChange={(e) => update("alert_email_recipients", e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
              Slack Webhook URL
            </label>
            <Input
              type="password"
              value={settings.alert_slack_webhook}
              placeholder="https://hooks.slack.com/..."
              onChange={(e) => update("alert_slack_webhook", e.target.value)}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
                Digest Frequency
              </label>
              <Select
                value={settings.alert_digest_frequency}
                onValueChange={(v) => {
                  if (v != null) update("alert_digest_frequency", v);
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
                Alert Tier Threshold
              </label>
              <Select
                value={settings.alert_tier_threshold}
                onValueChange={(v) => {
                  if (v != null) update("alert_tier_threshold", v);
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="medium">Medium+</SelectItem>
                  <SelectItem value="high">High+</SelectItem>
                  <SelectItem value="critical">Critical only</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex items-center gap-2 pt-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              disabled={
                isPending ||
                !settings.alert_slack_webhook ||
                settings.alert_slack_webhook === "••••••••"
              }
              onClick={() => testAlert("slack")}
            >
              Test Slack
            </Button>
            <Button
              variant="outline"
              size="sm"
              type="button"
              disabled={isPending || !settings.alert_email_recipients}
              onClick={() => testAlert("email")}
            >
              Test Email
            </Button>
            {testResult && (
              <span
                className={`text-sm ${testResult.includes("failed") ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400"}`}
                aria-live="polite"
              >
                {testResult}
              </span>
            )}
          </div>
        </div>
      </Card>

      {/* Save */}
      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={isPending}>
          <Save className="mr-2 h-4 w-4" />
          {isPending ? "Saving..." : "Save Settings"}
        </Button>
        {saved && (
          <span
            className="text-sm text-green-600 dark:text-green-400"
            aria-live="polite"
          >
            Settings saved
          </span>
        )}
      </div>
    </div>
  );
}
