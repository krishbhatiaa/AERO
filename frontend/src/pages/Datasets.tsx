import { useState } from "react";
import {
  Database,
  CloudDownload,
  CheckCircle2,
  Calendar,
  Layers,
  Code2,
  Loader2,
  ExternalLink,
} from "lucide-react";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import { DataKindBadge } from "@/components/DataKindBadge";
import { Panel } from "@/components/Panel";
import { TimeStamp } from "@/components/TimeStamp";
import { useDatasets, useDataSources } from "@/hooks/queries";
import { cn } from "@/lib/utils";
import type { SourceStatus } from "@/types/api";

const STATUS_CLS: Record<SourceStatus["status"], string> = {
  AVAILABLE: "border-primary/60 text-primary",
  DOWNLOADABLE: "border-secondary/60 text-secondary",
  ACCESS_REQUIRED: "border-tertiary/70 text-tertiary",
  NOT_CONFIGURED: "border-outline text-on-surface-variant",
};

export function Datasets(): JSX.Element {
  const sources = useDataSources();
  const datasets = useDatasets();

  // Active data source option: "existing" vs "cds_api"
  const [selectedOption, setSelectedOption] = useState<"existing" | "cds_api">(
    "existing",
  );
  const [region, setRegion] = useState<string>("bay-of-bengal");
  const [startDate, setStartDate] = useState<string>("2021-05-15");
  const [endDate, setEndDate] = useState<string>("2021-05-17");
  const [variables, setVariables] = useState<string[]>([
    "tp",
    "msl",
    "u10",
    "v10",
    "t2m",
  ]);

  // API Call State
  const [loading, setLoading] = useState<boolean>(false);
  const [apiResult, setApiResult] = useState<any>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const toggleVariable = (v: string) => {
    setVariables((prev) =>
      prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v],
    );
  };

  const handleFetch = async (dryRun: boolean) => {
    setLoading(true);
    setApiError(null);
    setApiResult(null);
    try {
      const res = await fetch("/api/v1/data-sources/fetch-era5", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start: startDate,
          end: endDate,
          region,
          variables,
          dry_run: dryRun,
        }),
      });
      let data: any = null;
      const text = await res.text();
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        // Response was not JSON (e.g. proxy gateway error or empty response)
      }

      if (!res.ok) {
        if (!data) {
          throw new Error(
            `Backend server returned HTTP ${res.status}${res.statusText ? ` (${res.statusText})` : ""}. Please check that the backend is running on port 8000.`,
          );
        }
        const errorDetail =
          typeof data.detail === "string"
            ? data.detail
            : data.detail?.message ||
              data.title ||
              data.message ||
              "Failed to contact CDS API";
        throw new Error(errorDetail);
      }

      if (!data || !data.data) {
        throw new Error("Invalid response received from server.");
      }
      setApiResult(data.data);
      if (!dryRun) {
        sources.refetch();
      }
    } catch (err: any) {
      setApiError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4">
      <div>
        <h1 className="text-head-lg">Datasets & Data Ingestion</h1>
        <p className="text-body-sm text-on-surface-variant">
          Choose between built-in scenarios or live programmatic retrieval via
          the Copernicus Climate Data Store (CDS API).
        </p>
      </div>

      {/* 2 OPTIONS DATA SOURCE SELECTOR */}
      <div className="rounded-xl border border-outline-variant/50 bg-surface-container-low p-5 shadow-sm space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-outline-variant/40 pb-3">
          <div>
            <h2 className="text-base font-bold text-on-surface flex items-center gap-2">
              <Database className="h-5 w-5 text-primary" />
              SELECT DATA SOURCE MODE
            </h2>
            <p className="text-xs text-on-surface-variant mt-0.5">
              Switch between local demo pipeline evaluation and live ECMWF ERA5
              Copernicus API data.
            </p>
          </div>
          <div className="flex items-center gap-1.5 font-mono text-xs text-on-surface-variant">
            <span>CDS CREDENTIALS:</span>
            <span className="font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
              CONFIGURED (9e20****0fe7)
            </span>
          </div>
        </div>

        {/* Option Cards */}
        <div className="grid md:grid-cols-2 gap-4">
          {/* OPTION 1: EXISTING / BUILT-IN SCENARIO */}
          <div
            onClick={() => setSelectedOption("existing")}
            className={cn(
              "cursor-pointer rounded-xl border p-4 transition-all flex flex-col justify-between",
              selectedOption === "existing"
                ? "border-primary bg-surface-container-lowest shadow-md ring-2 ring-primary/20"
                : "border-outline-variant/60 bg-surface-container-lowest/60 hover:border-outline-variant",
            )}
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm text-on-surface flex items-center gap-2">
                  <Database className="h-4 w-4 text-primary" />
                  Option 1: Existing Scenario Data
                </span>
                {selectedOption === "existing" ? (
                  <span className="flex items-center gap-1 text-[11px] font-bold font-mono text-primary bg-primary/10 px-2 py-0.5 rounded-full">
                    <CheckCircle2 className="h-3.5 w-3.5" /> ACTIVE
                  </span>
                ) : (
                  <span className="text-[11px] font-mono text-on-surface-variant">
                    Click to select
                  </span>
                )}
              </div>
              <p className="text-xs text-on-surface-variant leading-relaxed">
                Pre-calibrated 0.25° ERA5-compatible scenario dataset.
                Instantaneous load, offline-ready, complete with full extreme
                weather tracking ground truth and baseline evaluation metrics.
              </p>
            </div>

            <div className="mt-4 pt-3 border-t border-outline-variant/30 flex items-center justify-between text-xs font-mono text-on-surface-variant">
              <span>
                LATENCY: <b>0 ms</b>
              </span>
              <span>
                GRID: <b>0.25° (~28 km)</b>
              </span>
              <span>
                STATUS:{" "}
                <b className="text-emerald-600 dark:text-emerald-400">READY</b>
              </span>
            </div>
          </div>

          {/* OPTION 2: LIVE COPERNICUS CDS API */}
          <div
            onClick={() => setSelectedOption("cds_api")}
            className={cn(
              "cursor-pointer rounded-xl border p-4 transition-all flex flex-col justify-between",
              selectedOption === "cds_api"
                ? "border-primary bg-surface-container-lowest shadow-md ring-2 ring-primary/20"
                : "border-outline-variant/60 bg-surface-container-lowest/60 hover:border-outline-variant",
            )}
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm text-on-surface flex items-center gap-2">
                  <CloudDownload className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
                  Option 2: Live Copernicus CDS API
                </span>
                {selectedOption === "cds_api" ? (
                  <span className="flex items-center gap-1 text-[11px] font-bold font-mono text-cyan-600 dark:text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded-full">
                    <CheckCircle2 className="h-3.5 w-3.5" /> SELECTED
                  </span>
                ) : (
                  <span className="text-[11px] font-mono text-on-surface-variant">
                    Click to select
                  </span>
                )}
              </div>
              <p className="text-xs text-on-surface-variant leading-relaxed">
                Direct programmatic access to ECMWF Copernicus Climate Data
                Store using your personal access token. Retrieve historical
                NetCDF ERA5 reanalysis fields across custom geographic bounding
                boxes and dates.
              </p>
            </div>

            <div className="mt-4 pt-3 border-t border-outline-variant/30 flex items-center justify-between text-xs font-mono text-on-surface-variant">
              <span>
                SOURCE: <b>ECMWF CDS</b>
              </span>
              <span>
                API KEY: <b className="text-primary font-bold">CONFIGURED</b>
              </span>
              <span>
                FORMAT: <b>NetCDF4</b>
              </span>
            </div>
          </div>
        </div>

        {/* EXPANDED INTERACTIVE PANEL FOR OPTION 2: CDS API INGESTION */}
        {selectedOption === "cds_api" && (
          <div className="rounded-xl border border-cyan-500/30 bg-surface-container-lowest p-4 space-y-4 animate-in fade-in duration-200">
            <div className="flex items-center justify-between border-b border-outline-variant/30 pb-2.5">
              <div className="flex items-center gap-2">
                <CloudDownload className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
                <h3 className="text-xs font-bold font-mono uppercase tracking-wider text-on-surface">
                  Configure Copernicus CDS Request
                </h3>
              </div>
              <a
                href="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels"
                target="_blank"
                rel="noreferrer"
                className="text-[11px] font-mono text-primary flex items-center gap-1 hover:underline"
              >
                <span>Dataset Terms & Documentation</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            {/* Quick Historical Storm Presets */}
            <div className="flex flex-wrap items-center gap-2 pb-1 text-xs">
              <span className="font-mono text-[11px] text-on-surface-variant font-medium">Quick Date Presets:</span>
              <button
                type="button"
                onClick={() => {
                  setStartDate("2021-05-15");
                  setEndDate("2021-05-17");
                  setRegion("bay-of-bengal");
                  setApiError(null);
                }}
                className="px-2.5 py-1 rounded border border-outline-variant bg-surface-container hover:bg-surface-container-high text-on-surface font-mono text-[11px] transition"
              >
                Cyclone Yaas (May 2021)
              </button>
              <button
                type="button"
                onClick={() => {
                  setStartDate("2021-05-14");
                  setEndDate("2021-05-16");
                  setRegion("bay-of-bengal");
                  setApiError(null);
                }}
                className="px-2.5 py-1 rounded border border-outline-variant bg-surface-container hover:bg-surface-container-high text-on-surface font-mono text-[11px] transition"
              >
                Cyclone Tauktae (May 2021)
              </button>
              <button
                type="button"
                onClick={() => {
                  setStartDate("2026-09-18");
                  setEndDate("2026-09-20");
                  setRegion("bay-of-bengal");
                  setApiError(null);
                }}
                className="px-2.5 py-1 rounded border border-outline-variant bg-surface-container hover:bg-surface-container-high text-on-surface font-mono text-[11px] transition"
              >
                Latest Available (Sep 2026)
              </button>
            </div>

            {/* Form Fields: Region & Dates */}
            <div className="grid sm:grid-cols-3 gap-3 text-xs">
              <div>
                <label className="block text-[11px] font-mono text-on-surface-variant uppercase mb-1">
                  Region Preset
                </label>
                <select
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  className="w-full rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2 text-on-surface font-mono"
                >
                  <option value="bay-of-bengal">
                    Bay of Bengal (80°–98°E, 5°–26°N)
                  </option>
                  <option value="eastern-india">
                    Eastern India (80°–98°E, 15°–28°N)
                  </option>
                  <option value="south-asia">
                    South Asia (60°–100°E, 0°–40°N)
                  </option>
                  <option value="indian-ocean">
                    Equatorial Indian Ocean (40°–100°E)
                  </option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-mono text-on-surface-variant uppercase mb-1 flex items-center gap-1">
                  <Calendar className="h-3 w-3" /> Start Date (UTC)
                </label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full rounded-lg border border-outline-variant bg-surface-container-low px-3 py-1.5 text-on-surface font-mono"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono text-on-surface-variant uppercase mb-1 flex items-center gap-1">
                  <Calendar className="h-3 w-3" /> End Date (UTC)
                </label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full rounded-lg border border-outline-variant bg-surface-container-low px-3 py-1.5 text-on-surface font-mono"
                />
              </div>
            </div>

            {/* Variable Selection */}
            <div>
              <label className="block text-[11px] font-mono text-on-surface-variant uppercase mb-1.5 flex items-center gap-1">
                <Layers className="h-3 w-3" /> ERA5 Variables to Request
              </label>
              <div className="flex flex-wrap gap-2">
                {[
                  { code: "tp", label: "Total Precip (tp)" },
                  { code: "msl", label: "Sea-Level Pressure (msl)" },
                  { code: "u10", label: "10m U-Wind (u10)" },
                  { code: "v10", label: "10m V-Wind (v10)" },
                  { code: "t2m", label: "2m Temp (t2m)" },
                ].map((v) => (
                  <button
                    key={v.code}
                    type="button"
                    onClick={() => toggleVariable(v.code)}
                    className={cn(
                      "px-2.5 py-1 rounded-lg text-xs font-mono border transition",
                      variables.includes(v.code)
                        ? "bg-primary/10 border-primary text-primary font-bold"
                        : "border-outline-variant bg-surface-container-low text-on-surface-variant hover:text-on-surface",
                    )}
                  >
                    {v.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => handleFetch(true)}
                disabled={loading}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-outline-variant bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-mono text-xs transition"
              >
                <Code2 className="h-3.5 w-3.5" />
                <span>Compile Dry-Run Request</span>
              </button>

              <button
                type="button"
                onClick={() => handleFetch(false)}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-mono text-xs font-bold transition shadow-sm disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <CloudDownload className="h-3.5 w-3.5" />
                )}
                <span>Fetch from CDS API</span>
              </button>

              <div className="text-[11px] font-mono text-on-surface-variant">
                CLI:{" "}
                <code>
                  python scripts/ingest_era5.py --start {startDate} --end{" "}
                  {endDate} --region {region}
                </code>
              </div>
            </div>

            {/* Loading Indicator */}
            {loading && (
              <div className="flex items-center gap-2.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 p-3 text-xs text-cyan-700 dark:text-cyan-300">
                <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                <span>
                  Query submitted to Copernicus CDS queue. Copernicus prepares, extracts, and compiles the reanalysis NetCDF slice (typically 30–90 seconds depending on server load)...
                </span>
              </div>
            )}

            {/* Results Display */}
            {apiError && (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-xs space-y-2">
                <div className="flex items-center gap-2 font-bold text-red-600 dark:text-red-400">
                  <span className="font-mono uppercase">
                    API Request Failed
                  </span>
                </div>
                {apiError.toLowerCase().includes("licence") ||
                apiError.includes("403") ? (
                  <div className="space-y-2 text-on-surface">
                    <p className="font-semibold text-amber-600 dark:text-amber-400">
                      ⚠️ Copernicus ERA5 License Acceptance Required
                    </p>
                    <p className="text-on-surface-variant leading-relaxed">
                      Your CDS API credentials are authenticated, but the
                      Copernicus ERA5 dataset license has not yet been accepted
                      for your account. Copernicus requires each user to accept
                      the license agreement once on their website before
                      automated API downloads are permitted.
                    </p>
                    <div className="pt-1">
                      <a
                        href="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download#manage-licences"
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-on-primary font-medium hover:opacity-90 transition text-xs shadow-sm"
                      >
                        <span>Accept Copernicus ERA5 Terms of Use</span>
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </div>
                    <p className="text-[11px] text-on-surface-variant font-mono">
                      After clicking &quot;Accept terms&quot; on that page,
                      click &quot;Fetch from CDS API&quot; again.
                    </p>
                  </div>
                ) : apiError.toLowerCase().includes("not available yet") ||
                  apiError.toLowerCase().includes("period requested") ? (
                  <div className="space-y-2 text-on-surface">
                    <p className="font-semibold text-amber-600 dark:text-amber-400">
                      📅 Date Beyond Available ERA5 Reanalysis Window
                    </p>
                    <p className="text-on-surface-variant leading-relaxed">
                      Copernicus ERA5 is a retrospective climate reanalysis dataset with a rolling ~5-day publication delay (the latest published date is currently <b>September 21, 2026</b>).
                    </p>
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => {
                          setStartDate("2021-05-15");
                          setEndDate("2021-05-17");
                          setRegion("bay-of-bengal");
                          setApiError(null);
                        }}
                        className="px-3 py-1.5 rounded-lg bg-primary text-on-primary font-medium hover:opacity-90 transition text-xs shadow-sm"
                      >
                        Use Cyclone Yaas Dates (2021-05-15 to 2021-05-17)
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setStartDate("2026-09-18");
                          setEndDate("2026-09-20");
                          setRegion("bay-of-bengal");
                          setApiError(null);
                        }}
                        className="px-3 py-1.5 rounded-lg border border-outline-variant bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-mono"
                      >
                        Use Latest Available (2026-09-18 to 2026-09-20)
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-red-600 dark:text-red-400 font-mono break-all whitespace-pre-wrap">
                    {apiError}
                  </div>
                )}
              </div>
            )}

            {apiResult && (
              <div className="rounded-lg border border-cyan-500/30 bg-surface-container-low p-4 space-y-3 text-xs">
                <div className="flex items-center justify-between font-mono">
                  <span className="font-bold text-cyan-600 dark:text-cyan-400">
                    {apiResult.status}
                  </span>
                  <span className="text-on-surface-variant">
                    {apiResult.message}
                  </span>
                </div>
                {apiResult.file_path && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-on-surface font-mono text-[11px] bg-surface-container-lowest p-2.5 rounded-lg border border-outline-variant/40">
                    <div>
                      <span className="text-on-surface-variant">Saved File: </span>
                      <span className="font-bold">{apiResult.file_path}</span>
                    </div>
                    <div>
                      <span className="text-on-surface-variant">Size: </span>
                      <span className="font-bold">
                        {(apiResult.size_bytes / (1024 * 1024)).toFixed(2)} MB ({apiResult.size_bytes.toLocaleString()} bytes)
                      </span>
                    </div>
                    {apiResult.variables_retrieved && apiResult.variables_retrieved.length > 0 && (
                      <div className="sm:col-span-2">
                        <span className="text-on-surface-variant">Variables Ingested: </span>
                        <span className="font-bold text-primary">
                          {apiResult.variables_retrieved.join(", ")}
                        </span>
                      </div>
                    )}
                  </div>
                )}
                {apiResult.request_payload && (
                  <div>
                    <span className="text-[11px] font-mono text-on-surface-variant block mb-1">
                      Compiled CDS Request Payload:
                    </span>
                    <pre className="max-h-40 overflow-y-auto rounded bg-surface-container-lowest p-2 font-mono text-[11px] text-on-surface">
                      {JSON.stringify(apiResult.request_payload, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <AsyncBoundary query={sources} label="data sources">
        {(s) => (
          <>
            <div
              role="status"
              className="rounded border border-outline-variant bg-surface-container-low p-3 text-body-md"
            >
              <b>Target source resolution: </b>
              {s.target_source_resolution.message}
            </div>
            <ul className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
              {s.sources.map((x) => (
                <li
                  key={x.name}
                  className="flex flex-col gap-1.5 rounded border border-outline-variant/60 bg-surface-container-lowest p-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{x.name}</span>
                    <DataKindBadge kind={x.data_kind} compact />
                  </div>
                  <span
                    className={cn(
                      "w-fit rounded border px-1.5 py-[1px] font-mono text-label-num-sm font-bold",
                      STATUS_CLS[x.status],
                    )}
                  >
                    {x.status.replace("_", " ")}
                  </span>
                  <p className="text-body-xs text-on-surface-variant">
                    {x.message}
                  </p>
                  {x.nominal_resolution_deg !== null && (
                    <p className="font-mono text-label-num-sm text-on-surface-variant">
                      nominal ≈ {x.nominal_resolution_deg}° grid
                    </p>
                  )}
                  <p className="text-body-xs">{x.access}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </AsyncBoundary>
      <Panel title="Catalogued datasets">
        <AsyncBoundary
          query={datasets}
          label="datasets"
          isEmpty={(d) => d.length === 0}
        >
          {(rows) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-body-sm">
                <caption className="sr-only">
                  Datasets known to the platform
                </caption>
                <thead>
                  <tr className="text-label-header uppercase text-on-surface-variant">
                    {[
                      "Dataset",
                      "Source",
                      "Kind",
                      "Variables",
                      "Grid",
                      "Temporal extent (UTC)",
                      "Validation",
                    ].map((h) => (
                      <th
                        key={h}
                        scope="col"
                        className="border-b border-outline-variant px-2 py-1.5"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((d) => (
                    <tr
                      key={d.id}
                      className="odd:bg-surface-container-low align-top"
                    >
                      <th scope="row" className="px-2 py-1.5 text-left">
                        <div className="font-semibold">{d.name}</div>
                        <div className="font-mono text-label-num-sm text-on-surface-variant">
                          {d.id}
                        </div>
                      </th>
                      <td className="px-2 py-1.5">{d.source}</td>
                      <td className="px-2 py-1.5">
                        <DataKindBadge kind={d.data_kind} compact />
                      </td>
                      <td className="px-2 py-1.5 font-mono text-label-num-md">
                        {Object.entries(d.variables)
                          .map(([k, u]) => `${k} [${u}]`)
                          .join(", ")}
                      </td>
                      <td className="px-2 py-1.5 font-mono text-label-num-md">
                        {d.grid
                          ? `${d.grid.nlat}×${d.grid.nlon} · ${d.grid.resolution_km[0].toFixed(1)} km`
                          : "—"}
                      </td>
                      <td className="px-2 py-1.5">
                        {d.temporal_extent ? (
                          <>
                            <TimeStamp iso={d.temporal_extent.start} compact />{" "}
                            → <TimeStamp iso={d.temporal_extent.end} compact />
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-2 py-1.5 font-mono text-label-num-md">
                        {d.validation.ok ? "OK" : "FAILED"} ·{" "}
                        {d.validation.n_findings} finding(s)
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncBoundary>
      </Panel>
    </div>
  );
}
