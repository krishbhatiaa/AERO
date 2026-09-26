import React, { useEffect, useRef, useState } from "react";
import { Globe, ChevronDown, Search, Check } from "lucide-react";

declare global {
  interface Window {
    google: any;
    googleTranslateElementInit: () => void;
  }
}

const LANGUAGES = [
  { code: "en", label: "English",    region: "EN" },
  { code: "hi", label: "हिन्दी",      region: "HI" },
  { code: "ta", label: "தமிழ்",       region: "TA" },
  { code: "te", label: "తెలుగు",      region: "TE" },
  { code: "mr", label: "मराठी",       region: "MR" },
  { code: "gu", label: "ગુજરાતી",    region: "GU" },
  { code: "or", label: "ଓଡ଼ିଆ",       region: "OR" },
  { code: "bn", label: "বাংলা",       region: "BN" },
  { code: "ar", label: "العربية",    region: "AR" },
];

interface LanguageProps {
  direction?: "up" | "down";
  className?: string;
  fullWidth?: boolean;
  showLabel?: boolean;
}

type LangOption = (typeof LANGUAGES)[number];

const Language: React.FC<LanguageProps> = ({
  direction = "down",
  className = "",
  fullWidth = false,
  showLabel = false,
}) => {
  const [isOpen, setIsOpen]     = useState(false);
  const [selected, setSelected] = useState<LangOption>(LANGUAGES[0]!);
  const [searchQuery, setSearchQuery] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  /* ── Bootstrap Google Translate widget (hidden) ───────────────────────── */
  useEffect(() => {
    window.googleTranslateElementInit = () => {
      try {
        if (
          window.google?.translate?.TranslateElement &&
          typeof window.google.translate.TranslateElement === "function"
        ) {
          new window.google.translate.TranslateElement(
            { pageLanguage: "en", autoDisplay: false },
            "gt_hidden_element"
          );
        }
      } catch (err) {
        console.warn("Google Translate initialization failed:", err);
      }
    };

    if (!document.querySelector('script[src*="translate.google.com"]')) {
      const script = document.createElement("script");
      script.src =
        "https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit";
      script.async = true;
      document.body.appendChild(script);
    } else if (
      window.google?.translate?.TranslateElement &&
      typeof window.google.translate.TranslateElement === "function"
    ) {
      window.googleTranslateElementInit();
    }

    /* Suppress the GT banner bar */
    if (!document.getElementById("gt-suppress")) {
      const style = document.createElement("style");
      style.id = "gt-suppress";
      style.textContent = `
        .goog-te-banner-frame, #\\:1\\.container { display: none !important; }
        body { top: 0 !important; }
      `;
      document.head.appendChild(style);
    }

    return () => {
      // @ts-ignore
      delete window.googleTranslateElementInit;
    };
  }, []);

  /* ── Close on outside click ───────────────────────────────────────────── */
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  /* ── Drive the hidden GT combo-box ───────────────────────────────────── */
  const switchLanguage = (lang: (typeof LANGUAGES)[0]) => {
    setSelected(lang);
    setIsOpen(false);
    setSearchQuery("");

    const select = document.querySelector<HTMLSelectElement>(".goog-te-combo");
    if (select) {
      select.value = lang.code;
      select.dispatchEvent(new Event("change"));
    }
  };

  const filteredLanguages = LANGUAGES.filter(
    (lang) =>
      lang.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
      lang.code.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      {/* Hidden GT mount point */}
      <div id="gt_hidden_element" className="hidden" aria-hidden="true" />

      {/* ── Trigger button ──────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-label="Select language"
        title="Select Language"
        className={
          fullWidth
            ? "notranslate flex items-center justify-between w-full h-9 px-3 rounded-lg border border-outline-variant/60 bg-surface-container-low hover:bg-surface-container text-on-surface text-xs font-medium transition cursor-pointer shadow-sm"
            : "notranslate flex items-center gap-1.5 h-8 px-2.5 rounded-lg border border-outline-variant bg-surface-container-lowest hover:bg-surface-container-low text-on-surface text-xs font-semibold uppercase transition-colors cursor-pointer shadow-[0_1px_2px_0_rgb(0,0,0,0.05)]"
        }
      >
        <div className="flex items-center gap-2 min-w-0">
          <Globe size={14} className="text-primary shrink-0" />
          {(fullWidth || showLabel) && (
            <span className="truncate text-xs font-medium text-on-surface">
              {selected.label}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[10px] font-mono px-1 py-0.2 rounded bg-primary/10 text-primary font-bold">
            {selected.region}
          </span>
          <ChevronDown
            size={12}
            className={`text-on-surface-variant transition-transform duration-150 ${
              isOpen ? "rotate-180" : ""
            }`}
          />
        </div>
      </button>

      {/* ── Dropdown ────────────────────────────────────────────────────── */}
      {isOpen && (
        <div
          role="listbox"
          aria-label="Language"
          className={`absolute ${
            direction === "up"
              ? "bottom-full mb-1.5 left-0"
              : "right-0 mt-1"
          } ${fullWidth ? "w-full min-w-[200px]" : "w-48"} rounded-xl border border-outline-variant bg-surface-container-lowest shadow-2xl z-[100] p-1`}
        >
          {/* Search */}
          <div className="p-1.5 border-b border-outline-variant">
            <div className="relative">
              <Search
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-on-surface-variant"
                size={12}
                aria-hidden="true"
              />
              <input
                type="text"
                placeholder="Search…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Search languages"
                className="w-full pl-7 pr-2.5 py-1 bg-surface border border-outline-variant rounded-md text-[11px] text-on-surface focus:outline-none focus:border-primary placeholder:text-on-surface-variant"
              />
            </div>
          </div>

          {/* Language list */}
          <div className="max-h-52 overflow-y-auto py-1 px-0.5 space-y-0.5 scrollbar-thin">
            {filteredLanguages.length > 0 ? (
              filteredLanguages.map((lang) => (
                <button
                  key={lang.code}
                  type="button"
                  role="option"
                  aria-selected={selected.code === lang.code}
                  onClick={() => switchLanguage(lang)}
                  className={`notranslate w-full flex items-center justify-between px-2.5 py-1.5 text-xs rounded-md transition-colors cursor-pointer ${
                    selected.code === lang.code
                      ? "bg-primary text-on-primary font-bold"
                      : "text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] opacity-70">
                      {lang.region}
                    </span>
                    <span className="font-semibold">{lang.label}</span>
                  </div>
                  {selected.code === lang.code && (
                    <Check size={13} className="text-on-primary" aria-hidden="true" />
                  )}
                </button>
              ))
            ) : (
              <p className="py-2 text-center text-[10px] text-on-surface-variant italic">
                No languages found
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Language;
