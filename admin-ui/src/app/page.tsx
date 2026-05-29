"use client";

import {
  Activity,
  AlertCircle,
  Bot,
  CheckCircle2,
  Clock3,
  Copy,
  ExternalLink,
  Eye,
  Gauge,
  Globe2,
  Image as ImageIcon,
  KeyRound,
  Loader2,
  Monitor,
  Play,
  Plus,
  RefreshCcw,
  RotateCw,
  Save,
  Server,
  Settings2,
  Square,
  Trash2,
  Wifi,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";

type Health = {
  worker_id: string;
  timestamp: string;
  cpu_percent: number;
  ram_percent: number;
  active_accounts: number;
  busy_accounts: number;
  queue: {
    ready: number;
    delayed: number;
    active: number;
    total_jobs: number;
  };
  extension_status?: {
    manifest_present?: boolean;
  };
};

type QueueSettings = {
  name: string;
  max_retries: number;
  retry_delay_seconds: number;
  scheduler_interval_seconds: number;
  job_timeout_seconds: number;
};

type FlowGenerationSettings = {
  model: string;
  duration?: number;
  estimated_credits: number;
  presets: Record<string, unknown>;
};

type FlowSettings = {
  text_to_image: FlowGenerationSettings;
  image_to_image: FlowGenerationSettings;
  text_to_video: FlowGenerationSettings;
  image_to_video: FlowGenerationSettings;
};

type Account = {
  id: string;
  status: string;
  proxy_enabled: boolean;
  proxy_url: string | null;
  jobs_running: number;
  health_score: number;
  browser_pid: number | null;
  remote_debugging_port: number | null;
  display: string | null;
  vnc_port: number | null;
  vnc_web_port: number | null;
  vnc_web_url: string | null;
  flowkit_ws_port: number | null;
  settings: {
    flow_url: string | null;
    max_concurrent_jobs: number;
    tags: string[];
  };
};

type Job = {
  id: string;
  prompt: string;
  generation_type?: string | null;
  flow_model?: string | null;
  duration?: number | null;
  estimated_credits?: number | null;
  output_urls?: string[];
  state: string;
  account_id: string | null;
  retries: number;
  max_retries: number;
  started_at?: string | null;
  completed_at?: string | null;
  queued_at: string;
  last_error: string | null;
  payload?: {
    flowkit_result?: {
      project_id?: string;
      image_media_id?: string;
      video_media_id?: string;
    };
  };
};

const DEFAULT_API = "/api/worker";

function cls(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(" ");
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${DEFAULT_API}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

function jobOutputUrls(job: Job) {
  return job.output_urls || [];
}

function jobOutcome(job: Job) {
  const urls = jobOutputUrls(job);
  if (job.state === "COMPLETED" && urls.length > 0) return { label: "OUTPUT READY", tone: "green" as const };
  if (job.state === "COMPLETED") return { label: "COMPLETED, NO OUTPUT", tone: "amber" as const };
  if (job.state === "FAILED" || job.state === "TIMEOUT") return { label: job.state, tone: "red" as const };
  return { label: job.state, tone: "amber" as const };
}

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [queue, setQueue] = useState<QueueSettings | null>(null);
  const [flowSettings, setFlowSettings] = useState<FlowSettings | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [accountId, setAccountId] = useState("acc-1");
  const [maxConcurrentJobs, setMaxConcurrentJobs] = useState(1);
  const [proxyEnabled, setProxyEnabled] = useState(false);
  const [proxyUrl, setProxyUrl] = useState("");
  const [flowUrl, setFlowUrl] = useState("https://labs.google/fx/tools/flow");

  const [queueDraft, setQueueDraft] = useState({
    max_retries: 3,
    retry_delay_seconds: 60,
    job_timeout_seconds: 900,
  });
  const selectedAccount = useMemo(
    () => accounts.find((account) => account.id === selectedAccountId) || accounts[0] || null,
    [accounts, selectedAccountId],
  );

  async function refresh(silent = false) {
    if (!silent) setLoading(true);
    try {
      const [nextHealth, nextQueue, nextFlowSettings, nextAccounts, nextJobs] = await Promise.all([
        api<Health>("/health"),
        api<QueueSettings>("/settings/queue"),
        api<FlowSettings>("/flow-settings"),
        api<Account[]>("/accounts"),
        api<Job[]>("/jobs?limit=25"),
      ]);
      setHealth(nextHealth);
      setQueue(nextQueue);
      setFlowSettings(nextFlowSettings);
      setQueueDraft({
        max_retries: nextQueue.max_retries,
        retry_delay_seconds: nextQueue.retry_delay_seconds,
        job_timeout_seconds: nextQueue.job_timeout_seconds,
      });
      setAccounts(nextAccounts);
      setJobs(nextJobs);
      if (!selectedAccountId && nextAccounts[0]) setSelectedAccountId(nextAccounts[0].id);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reach worker API");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const boot = window.setTimeout(() => refresh(), 0);
    const id = window.setInterval(() => refresh(true), 10000);
    return () => {
      window.clearTimeout(boot);
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runAction(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    setNotice(null);
    setError(null);
    try {
      await action();
      setNotice(label);
      await refresh(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runAction("Account created", () =>
      api<Account>("/accounts", {
        method: "POST",
        body: JSON.stringify({
          id: accountId.trim() || undefined,
          proxy_enabled: proxyEnabled,
          proxy_url: proxyEnabled ? proxyUrl || null : null,
          settings: {
            flow_url: flowUrl || null,
            max_concurrent_jobs: maxConcurrentJobs,
          },
        }),
      }),
    );
  }

  async function updateQueue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runAction("Queue settings saved", () =>
      api<QueueSettings>("/settings/queue", {
        method: "PATCH",
        body: JSON.stringify(queueDraft),
      }),
    );
  }

  async function updateAccountConcurrency(account: Account, value: number) {
    await runAction("Account concurrency saved", () =>
      api<Account>(`/accounts/${encodeURIComponent(account.id)}/settings`, {
        method: "PATCH",
        body: JSON.stringify({ max_concurrent_jobs: value }),
      }),
    );
  }

  async function copy(text: string) {
    await navigator.clipboard.writeText(text);
    setNotice("Copied to clipboard");
  }

  const isBusy = Boolean(busy);

  return (
    <main className="min-h-screen bg-[#f6f7f9] text-slate-950">
      <div className="mx-auto flex min-h-screen w-full max-w-[1600px] flex-col px-4 py-4 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-slate-200 pb-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex size-11 items-center justify-center rounded-lg bg-slate-950 text-white">
                <Server size={22} />
              </div>
              <div>
                <h1 className="text-2xl font-semibold tracking-normal">Flow Worker Admin</h1>
                <p className="text-sm text-slate-500">Control panel for accounts, jobs, VNC, and queue behavior.</p>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <StatusPill ok={!error && Boolean(health)} label={error ? "API issue" : "Worker online"} />
            <button className="icon-button" onClick={() => refresh()} disabled={loading} title="Refresh data">
              <RefreshCcw size={17} className={loading ? "animate-spin" : ""} />
            </button>
            <a className="command-button" href="http://161.118.208.146/docs" target="_blank" rel="noreferrer">
              <ExternalLink size={16} />
              API docs
            </a>
          </div>
        </header>

        {(notice || error) && (
          <div className={cls("mt-4 flex items-center gap-2 rounded-lg border px-3 py-2 text-sm", error ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700")}>
            {error ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
            <span className="line-clamp-2">{error || notice}</span>
          </div>
        )}

        <section className="mt-5 grid gap-4 lg:grid-cols-4">
          <Metric icon={Activity} label="CPU" value={`${Math.round(health?.cpu_percent ?? 0)}%`} tone="green" />
          <Metric icon={Gauge} label="RAM" value={`${Math.round(health?.ram_percent ?? 0)}%`} tone="blue" />
          <Metric icon={Bot} label="Accounts" value={`${health?.active_accounts ?? accounts.length}`} tone="slate" />
          <Metric icon={Clock3} label="Queue" value={`${health?.queue.ready ?? 0} ready`} tone="amber" />
        </section>

        <div className="mt-5 grid flex-1 gap-5 xl:grid-cols-[420px_minmax(0,1fr)]">
          <aside className="flex flex-col gap-5">
            <Panel title="Create Account" icon={Plus}>
              <form className="grid gap-3" onSubmit={createAccount}>
                <Field label="Account ID">
                  <input className="input" value={accountId} onChange={(event) => setAccountId(event.target.value)} placeholder="acc-1 or email" />
                </Field>
                <Field label="Flow URL">
                  <input className="input" value={flowUrl} onChange={(event) => setFlowUrl(event.target.value)} />
                </Field>
                <Field label="Concurrent jobs">
                  <Stepper value={maxConcurrentJobs} min={1} max={5} onChange={setMaxConcurrentJobs} />
                </Field>
                <label className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
                  <span className="flex items-center gap-2 font-medium"><Globe2 size={16} /> Proxy</span>
                  <input type="checkbox" checked={proxyEnabled} onChange={(event) => setProxyEnabled(event.target.checked)} />
                </label>
                {proxyEnabled && (
                  <Field label="Proxy URL">
                    <input className="input" value={proxyUrl} onChange={(event) => setProxyUrl(event.target.value)} placeholder="http://user:pass@host:8080" />
                  </Field>
                )}
                <button className="primary-button" disabled={isBusy}>
                  {isBusy ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
                  Create and start
                </button>
              </form>
            </Panel>

            <Panel title="Queue Settings" icon={Settings2}>
              <form className="grid gap-3" onSubmit={updateQueue}>
                <NumberField label="Max retries" value={queueDraft.max_retries} min={0} max={20} onChange={(value) => setQueueDraft({ ...queueDraft, max_retries: value })} />
                <NumberField label="Retry delay seconds" value={queueDraft.retry_delay_seconds} min={0} max={3600} onChange={(value) => setQueueDraft({ ...queueDraft, retry_delay_seconds: value })} />
                <NumberField label="Job timeout seconds" value={queueDraft.job_timeout_seconds} min={60} max={7200} onChange={(value) => setQueueDraft({ ...queueDraft, job_timeout_seconds: value })} />
                <button className="command-button justify-center" disabled={isBusy}>
                  <Save size={16} />
                  Save queue settings
                </button>
              </form>
            </Panel>

            <Panel title="Model Policy" icon={Bot}>
              <div className="grid gap-3 text-sm">
                <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-blue-900">
                  Model settings are controlled globally from the orchestrator UI on port 3001. This worker page only manages local accounts, VNC, and queue behavior.
                </div>
                <a className="command-button justify-center" href="http://localhost:3001" target="_blank" rel="noreferrer">
                  <ExternalLink size={16} />
                  Open global model policy
                </a>
              </div>
            </Panel>

            <Panel title="Worker Snapshot" icon={Wifi}>
              <div className="grid gap-2 text-sm">
                <InfoRow label="Worker" value={health?.worker_id || "Unknown"} />
                <InfoRow label="Queue name" value={queue?.name || "flow_jobs"} />
                <InfoRow label="Video model" value={flowSettings?.text_to_video.model || "Unknown"} />
                <InfoRow label="Jobs total" value={String(health?.queue.total_jobs ?? 0)} />
                <InfoRow label="Active jobs" value={String(health?.queue.active ?? 0)} />
                <InfoRow label="Extension" value={health?.extension_status?.manifest_present ? "Ready" : "Missing"} />
              </div>
            </Panel>
          </aside>

          <section className="flex min-w-0 flex-col gap-5">
            <Panel title="Accounts" icon={Monitor} action={<span className="text-xs text-slate-500">{accounts.length} total</span>}>
              {accounts.length === 0 ? (
                <EmptyState title="No accounts yet" text="Create one from the left panel. The response will include a browser VNC link automatically." />
              ) : (
                <div className="grid gap-3">
                  {accounts.map((account) => (
                    <AccountRow
                      key={account.id}
                      account={account}
                      selected={selectedAccount?.id === account.id}
                      busy={isBusy}
                      onSelect={() => setSelectedAccountId(account.id)}
                      onStart={() => runAction("Account started", () => api(`/accounts/${encodeURIComponent(account.id)}/start`, { method: "POST" }))}
                      onStop={() => runAction("Account stopped", () => api(`/accounts/${encodeURIComponent(account.id)}/stop`, { method: "POST" }))}
                      onRestart={() => runAction("Account restarted", () => api(`/accounts/${encodeURIComponent(account.id)}/restart`, { method: "POST" }))}
                      onDelete={() => runAction("Account deleted", () => api(`/accounts/${encodeURIComponent(account.id)}?remove_profile=true`, { method: "DELETE" }))}
                      onCopy={() => account.vnc_web_url && copy(account.vnc_web_url)}
                      onConcurrency={(value) => updateAccountConcurrency(account, value)}
                    />
                  ))}
                </div>
              )}
            </Panel>

            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
              <Panel title="VNC Preview" icon={Eye}>
                {selectedAccount?.vnc_web_url ? (
                  <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-950">
                    <div className="flex items-center justify-between border-b border-white/10 px-3 py-2 text-sm text-white">
                      <span className="truncate">{selectedAccount.id}</span>
                      <a className="flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 hover:bg-white/15" href={selectedAccount.vnc_web_url} target="_blank" rel="noreferrer">
                        <ExternalLink size={14} />
                        Open
                      </a>
                    </div>
                    <iframe className="h-[520px] w-full bg-black" src={selectedAccount.vnc_web_url} title="VNC preview" />
                  </div>
                ) : (
                  <EmptyState title="Select an active account" text="Once an account starts, its noVNC browser link appears here." />
                )}
              </Panel>

              <Panel title="Recent Jobs" icon={Clock3}>
                {jobs.length === 0 ? (
                  <EmptyState title="No jobs yet" text="Submitted jobs will appear here with retry and state details." />
                ) : (
                  <div className="grid gap-2">
                    {jobs.map((job) => (
                      <WorkerJobCard key={job.id} job={job} />
                    ))}
                  </div>
                )}
              </Panel>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}

function WorkerJobCard({ job }: { job: Job }) {
  const urls = jobOutputUrls(job);
  const outcome = jobOutcome(job);
  const debugDetail =
    job.last_error ||
    (job.state === "COMPLETED" && urls.length === 0 ? "Worker reported COMPLETED but returned no output_urls. That means generation finished without a usable media URL, or extraction failed." : null);
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-center justify-between gap-2">
        <span className={cls("rounded-md px-2 py-1 text-xs font-semibold", outcome.tone === "green" ? "bg-emerald-50 text-emerald-700" : outcome.tone === "red" ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700")}>{outcome.label}</span>
        <span className="text-xs text-slate-500">{job.retries}/{job.max_retries}</span>
      </div>
      <p className="mt-2 line-clamp-3 text-sm font-medium text-slate-800">{job.prompt || job.id}</p>
      <p className="mt-1 text-xs text-slate-500">
        {job.generation_type || "generation"}{job.flow_model ? ` | ${job.flow_model}` : ""}{job.duration ? ` | ${job.duration}s` : ""}{job.estimated_credits !== undefined && job.estimated_credits !== null ? ` | ${job.estimated_credits} points` : ""}
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
        <MiniInfo label="Account" value={job.account_id || "pending"} warning={job.state === "COMPLETED" && !job.account_id} />
        <MiniInfo label="Outputs" value={String(urls.length)} warning={job.state === "COMPLETED" && urls.length === 0} />
        <MiniInfo label="Project" value={job.payload?.flowkit_result?.project_id || "pending"} />
        <MiniInfo label="Media" value={job.payload?.flowkit_result?.image_media_id || job.payload?.flowkit_result?.video_media_id || "pending"} />
      </div>
      {urls.length > 0 && (
        <div className="mt-3 overflow-hidden rounded-lg border border-emerald-200 bg-emerald-50">
          <a className="block bg-white" href={urls[0]} target="_blank" rel="noreferrer" title="Open generated output">
            {urls[0].includes("/image/") ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img className="h-36 w-full object-cover" src={urls[0]} alt="Generated output preview" />
            ) : (
              <div className="flex h-28 items-center justify-center text-slate-500"><ImageIcon size={26} /></div>
            )}
          </a>
          <div className="grid gap-2 p-2">
            {urls.map((url, index) => (
              <div key={url} className="flex min-w-0 items-center gap-2 rounded-md bg-white px-2 py-1.5">
                <span className="shrink-0 text-xs font-semibold text-slate-400">#{index + 1}</span>
                <a className="min-w-0 flex-1 truncate text-xs font-semibold text-blue-700 hover:underline" href={url} target="_blank" rel="noreferrer">{url}</a>
                <button className="icon-button !size-8 shrink-0" title="Copy output URL" onClick={() => navigator.clipboard.writeText(url)}>
                  <Copy size={14} />
                </button>
                <a className="icon-button !size-8 shrink-0" href={url} target="_blank" rel="noreferrer" title="Open output">
                  <ExternalLink size={14} />
                </a>
              </div>
            ))}
          </div>
        </div>
      )}
      {debugDetail && (
        <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <div className="font-semibold">Debug detail</div>
          <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px]">{debugDetail}</pre>
                        </div>
      )}
    </div>
  );
}

function Panel({ title, icon: Icon, children, action }: { title: string; icon: LucideIcon; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Icon size={17} />
          {title}
        </h2>
        {action}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Metric({ icon: Icon, label, value, tone }: { icon: LucideIcon; label: string; value: string; tone: "green" | "blue" | "slate" | "amber" }) {
  const colors = {
    green: "bg-emerald-50 text-emerald-700",
    blue: "bg-blue-50 text-blue-700",
    slate: "bg-slate-100 text-slate-700",
    amber: "bg-amber-50 text-amber-700",
  };
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-500">{label}</span>
        <span className={cls("flex size-8 items-center justify-center rounded-lg", colors[tone])}>
          <Icon size={17} />
        </span>
      </div>
      <div className="mt-3 text-2xl font-semibold">{value}</div>
    </div>
  );
}

function AccountRow(props: {
  account: Account;
  selected: boolean;
  busy: boolean;
  onSelect: () => void;
  onStart: () => void;
  onStop: () => void;
  onRestart: () => void;
  onDelete: () => void;
  onCopy: () => void;
  onConcurrency: (value: number) => void;
}) {
  const { account } = props;
  return (
    <div className={cls("rounded-lg border p-3 transition", props.selected ? "border-slate-950 bg-slate-50" : "border-slate-200 bg-white")}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <button className="min-w-0 text-left" onClick={props.onSelect}>
          <div className="flex items-center gap-2">
            <span className="truncate font-medium">{account.id}</span>
            <span className={cls("rounded-md px-2 py-0.5 text-xs", account.status === "READY" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700")}>{account.status}</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
            <span>VNC {account.vnc_port ?? "-"}</span>
            <span>Web {account.vnc_web_port ?? "-"}</span>
            <span>Health {account.health_score}</span>
            <span>Running {account.jobs_running}</span>
          </div>
        </button>
        <div className="flex flex-wrap items-center gap-2">
          <Stepper value={account.settings.max_concurrent_jobs} min={1} max={5} onChange={props.onConcurrency} compact />
          <IconButton title="Start" onClick={props.onStart} disabled={props.busy} icon={Play} />
          <IconButton title="Stop" onClick={props.onStop} disabled={props.busy} icon={Square} />
          <IconButton title="Restart" onClick={props.onRestart} disabled={props.busy} icon={RotateCw} />
          {account.vnc_web_url && (
            <>
              <IconButton title="Copy VNC URL" onClick={props.onCopy} disabled={props.busy} icon={Copy} />
              <a className="icon-button" href={account.vnc_web_url} target="_blank" rel="noreferrer" title="Open VNC">
                <ExternalLink size={16} />
              </a>
            </>
          )}
          <IconButton title="Delete account and profile" onClick={props.onDelete} disabled={props.busy} icon={Trash2} danger />
        </div>
      </div>
    </div>
  );
}

function IconButton({ title, onClick, disabled, icon: Icon, danger }: { title: string; onClick: () => void; disabled?: boolean; icon: LucideIcon; danger?: boolean }) {
  return (
    <button className={cls("icon-button", danger && "text-red-600 hover:border-red-200 hover:bg-red-50")} onClick={onClick} disabled={disabled} title={title}>
      <Icon size={16} />
    </button>
  );
}

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={cls("inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium", ok ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700")}>
      {ok ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
      {label}
    </span>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}

function NumberField({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (value: number) => void }) {
  return (
    <Field label={label}>
      <input className="input" type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </Field>
  );
}

function Stepper({ value, min, max, onChange, compact }: { value: number; min: number; max: number; onChange: (value: number) => void; compact?: boolean }) {
  return (
    <div className={cls("inline-grid grid-cols-[36px_44px_36px] overflow-hidden rounded-lg border border-slate-200 bg-white", compact ? "h-9" : "h-10")}>
      <button type="button" className="border-r border-slate-200 text-slate-600 hover:bg-slate-50" onClick={() => onChange(Math.max(min, value - 1))}>-</button>
      <div className="flex items-center justify-center text-sm font-semibold">{value}</div>
      <button type="button" className="border-l border-slate-200 text-slate-600 hover:bg-slate-50" onClick={() => onChange(Math.min(max, value + 1))}>+</button>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function MiniInfo({ label, value, warning }: { label: string; value: string; warning?: boolean }) {
  return (
    <div className={cls("rounded-lg px-2 py-1.5", warning ? "bg-amber-50" : "bg-slate-50")}>
      <div className={cls("text-[10px] font-semibold uppercase", warning ? "text-amber-500" : "text-slate-400")}>{label}</div>
      <div className={cls("mt-0.5 truncate text-xs font-semibold", warning ? "text-amber-800" : "text-slate-800")}>{value}</div>
    </div>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 px-6 py-8 text-center">
      <KeyRound className="mb-3 text-slate-400" size={24} />
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-slate-500">{text}</p>
    </div>
  );
}
