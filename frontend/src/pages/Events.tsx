import { useState } from "react";
import { Link } from "react-router-dom";
import { Calendar, Filter, MapPin, Search, TrendingUp, ArrowUpRight } from "lucide-react";

import { AsyncBoundary } from "@/components/AsyncBoundary";
import { DataKindBadge } from "@/components/DataKindBadge";
import { SeverityChip } from "@/components/SeverityChip";
import { TimeStamp } from "@/components/TimeStamp";
import { useEvents } from "@/hooks/queries";
import { useDebounce } from "@/hooks/useDebounce";
import { fmt, fmtInt } from "@/lib/utils";

export function Events(): JSX.Element {
  const [severity, setSeverity] = useState("");
  const [sort, setSort] = useState("-severity,-first_valid_time");
  const [text, setText] = useState("");
  const q = useEvents({ severity: severity || undefined, sort });
  const needle = useDebounce(text.trim().toLowerCase(), 250);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-on-surface flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <Calendar className="h-5 w-5 text-primary" />
            </div>
            Detected Events
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-on-surface-variant">
            Events extracted from anomaly fields and tracked through the forecast.
            Severity is an analytical category, not an official warning level.
          </p>
        </div>
        <DataKindBadge kind="SYNTHETIC_DEMO" />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-4 rounded-xl border border-outline-variant/40 bg-surface-container-lowest p-4">
        <div className="flex items-center gap-2 text-xs text-on-surface-variant">
          <Filter className="h-3.5 w-3.5" />
          <span className="font-medium uppercase tracking-wide">Filters</span>
        </div>
        <div>
          <label htmlFor="f-sev" className="block text-[10px] font-medium text-on-surface-variant uppercase tracking-wider mb-1">Severity</label>
          <select id="f-sev" value={severity} onChange={(e) => setSeverity(e.target.value)} className="rounded-lg border border-outline-variant bg-surface-container-lowest px-3 py-1.5 text-sm font-mono focus:border-primary focus:ring-1 focus:ring-primary/30">
            <option value="">All Severities</option>
            <option>LOW</option>
            <option>MODERATE</option>
            <option>SEVERE</option>
          </select>
        </div>
        <div>
          <label htmlFor="f-sort" className="block text-[10px] font-medium text-on-surface-variant uppercase tracking-wider mb-1">Sort By</label>
          <select id="f-sort" value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-lg border border-outline-variant bg-surface-container-lowest px-3 py-1.5 text-sm font-mono focus:border-primary focus:ring-1 focus:ring-primary/30">
            <option value="-severity,-first_valid_time">Severity (high first)</option>
            <option value="-peak_intensity">Peak Intensity</option>
            <option value="-max_area_km2">Area</option>
            <option value="first_valid_time">Start Time</option>
          </select>
        </div>
        <div className="min-w-[200px] grow">
          <label htmlFor="f-text" className="block text-[10px] font-medium text-on-surface-variant uppercase tracking-wider mb-1">Search</label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-on-surface-variant" />
            <input id="f-text" value={text} onChange={(e) => setText(e.target.value)} placeholder="Filter by ID or type..." className="w-full rounded-lg border border-outline-variant bg-surface-container-lowest py-1.5 pl-9 pr-3 text-sm font-mono focus:border-primary focus:ring-1 focus:ring-primary/30" />
          </div>
        </div>
      </div>

      {/* Events List */}
      <AsyncBoundary query={q} label="events" isEmpty={(d) => d.length === 0} emptyText="No events match these filters.">
        {(all) => {
          const rows = all.filter((e) => !needle || e.id.includes(needle) || e.event_type.toLowerCase().includes(needle));
          return (
            <div className="space-y-3">
              {rows.length === 0 ? (
                <div className="rounded-xl border border-outline-variant/40 bg-surface-container-lowest p-8 text-center">
                  <p className="text-on-surface-variant">No events match "{needle}".</p>
                </div>
              ) : (
                rows.map((e) => (
                  <Link
                    key={e.id}
                    to={`/events/${e.id}`}
                    className="group block rounded-xl border border-outline-variant/40 bg-surface-container-lowest p-4 transition-all hover:border-primary/40 hover:shadow-lg hover:shadow-primary/5"
                  >
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <div className="flex items-center gap-4">
                        <SeverityChip severity={e.severity} />
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-on-surface">{e.event_type.replace("_", " ")}</span>
                            <span className="rounded bg-surface-container px-1.5 py-0.5 font-mono text-[10px] text-on-surface-variant">{e.id.slice(0, 8)}</span>
                          </div>
                          <div className="mt-1 flex items-center gap-3 text-xs text-on-surface-variant">
                            <span className="flex items-center gap-1"><Calendar className="h-3 w-3" /><TimeStamp iso={e.first_valid_time} compact /></span>
                            <span>→</span>
                            <TimeStamp iso={e.last_valid_time} compact />
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-on-surface-variant">
                        <div className="text-right">
                          <div className="flex items-center gap-1 font-mono text-sm font-semibold text-on-surface">
                            <TrendingUp className="h-3 w-3 text-primary" />
                            {fmt(e.peak_intensity.value, 0)} {e.peak_intensity.unit}
                          </div>
                          <div className="text-[10px]">Peak intensity</div>
                        </div>
                        <div className="text-right">
                          <div className="flex items-center gap-1 font-mono text-sm font-semibold text-on-surface">
                            <MapPin className="h-3 w-3 text-primary" />
                            {fmtInt(e.max_area_km2)} km²
                          </div>
                          <div className="text-[10px]">Max area</div>
                        </div>
                        <DataKindBadge kind={e.data_kind} compact />
                        <ArrowUpRight className="h-4 w-4 text-on-surface-variant transition group-hover:text-primary" />
                      </div>
                    </div>
                  </Link>
                ))
              )}
            </div>
          );
        }}
      </AsyncBoundary>
    </div>
  );
}
