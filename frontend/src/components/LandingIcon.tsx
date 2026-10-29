import type { ReactElement } from "react";

/** Icon paths shared by the public pages. */
export const ICONS: Record<string, string> = {
  lock: "M7 11V8a5 5 0 0 1 10 0v3M6 11h12v9H6z",
  layers: "m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5m-18 4 9 5 9-5",
  cookie:
    "M12 3a9 9 0 1 0 9 9 4 4 0 0 1-4-4 4 4 0 0 1-5-5Zm-3 9h.01M13 16h.01M9 16h.01M14 12h.01",
  cert: "M5 4h14v11H5zM9 20l3-3 3 3v-5H9zM8 8h8M8 11h5",
  file: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  chart: "M4 20V10m6 10V4m6 16v-7m4 7H2",
  proof: "m5 12 4 4L19 6M4 20h16",
  cycle:
    "M4 12a8 8 0 0 1 14-5l2 2M20 4v5h-5M20 12a8 8 0 0 1-14 5l-2-2m0 5v-5h5",
  doc: "M6 3h9l4 4v14H6zM9 12h7M9 16h7M9 8h3",
  users:
    "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-6 9a6 6 0 0 1 12 0M17 11a3 3 0 1 0 0-6M21 20a6 6 0 0 0-4-5.6",
  log: "M5 4h14v16H5zM9 9h6M9 13h6M9 17h3",
  folder: "M3 6h6l2 2h10v11H3zM3 6v13",
  scan: "M4 8V4h4M20 8V4h-4M4 16v4h4m12-4v4h-4M8 12h8",
  review: "M5 4h14v16H5zM8 9h8M8 13h5m2 4 2 2 3-3",
  fix: "m14 6 4 4-9 9H5v-4zM12 8l4 4",
};

export function Icon({ name }: { name: string }): ReactElement {
  return (
    <span className="landing-icon" aria-hidden="true">
      <svg
        viewBox="0 0 24 24"
        width="22"
        height="22"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={ICONS[name] ?? ICONS.lock} />
      </svg>
    </span>
  );
}
