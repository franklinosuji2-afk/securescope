/**
 * Explanatory guidance for each finding type. This is static, reviewed text keyed by the scanner's
 * finding id; it never contains scan data. The text lives in guidance.json, which is an exact copy of
 * the file the PDF report uses (a backend test keeps the two equal). Anything observed about a target
 * comes from the backend.
 */
import data from "./guidance.json";

export interface FixExample {
  label: string;
  code: string;
}

export interface Guidance {
  impact: string;
  detection: "observed" | "heuristic";
  detectionNote: string;
  fixes: FixExample[];
  verify: string[];
  references: { label: string; url: string }[];
  limitations: string;
}

const FIND = data as unknown as Record<string, Guidance>;

const GENERIC: Guidance = {
  impact: "See the description for what was observed and why it matters.",
  detection: "observed",
  detectionNote: "Reported by a passive check of the scanned response.",
  fixes: [],
  verify: [
    "Apply the recommended fix, then run a new scan. The finding is only treated as resolved when a later scan no longer reports it.",
  ],
  references: [],
  limitations:
    "SecureScope runs a limited set of passive checks on a single page.",
};

export function guidanceFor(findingId: string): Guidance {
  return FIND[findingId] ?? GENERIC;
}
