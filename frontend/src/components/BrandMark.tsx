// The SecureScope mark: a shield with a stylised S. One component so every page draws the same logo.
// The same drawing is in public/favicon.svg and the app icons, and in the PDF report template.
export const BRAND_S_PATH =
  "M20.4 11.3C19.5 10 17.9 9.2 16 9.2c-2.4 0-4.2 1.2-4.2 3.1 0 1.9 1.6 2.6 4.2 3.3 2.6.7 4.2 1.5 4.2 3.5 0 1.9-1.8 3.2-4.2 3.2-2.1 0-3.8-.9-4.7-2.4";

export default function BrandMark({
  className,
  size,
  shield = "var(--accent-soft)",
}: {
  className?: string;
  size?: number;
  shield?: string;
}) {
  return (
    <svg
      className={className}
      viewBox="0 0 32 32"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M16 3 5 7v8c0 7 4.6 11.7 11 14 6.4-2.3 11-7 11-14V7L16 3Z"
        fill="none"
        strokeWidth="2.2"
        strokeLinejoin="round"
        style={{ stroke: shield }}
      />
      <path
        d={BRAND_S_PATH}
        fill="none"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ stroke: "var(--ok)" }}
      />
    </svg>
  );
}
