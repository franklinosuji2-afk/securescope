import { useEffect, useState } from "react";

const R = 52;
const C = 2 * Math.PI * R;

/**
 * A ring for a 0 to 100 score. The number is real text next to the ring and in the image label, so the
 * ring is only a picture of it. It fills once on mount; reduced-motion users get the final state at once.
 */
export default function SecurityScoreGauge({
  score,
  grade,
  host,
}: {
  score: number;
  grade: string | null;
  host: string;
}) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setShown(score));
    return () => cancelAnimationFrame(frame);
  }, [score]);
  const clamped = Math.min(100, Math.max(0, shown));
  const band = score >= 75 ? "good" : score >= 50 ? "fair" : "poor";
  return (
    <div className="gauge">
      <svg
        viewBox="0 0 120 120"
        className={`gauge-svg gauge-${band}`}
        role="img"
        aria-label={`Heuristic score ${score} out of 100${grade ? `, grade ${grade}` : ""}, for ${host}`}
      >
        <circle cx="60" cy="60" r={R} className="gauge-track" />
        <circle
          cx="60"
          cy="60"
          r={R}
          className="gauge-arc"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - clamped / 100)}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div className="gauge-read" aria-hidden="true">
        <span className="gauge-num">{score}</span>
        <span className="gauge-of">/ 100</span>
      </div>
    </div>
  );
}
