import { formatDate } from "../format";
import { chartPoints, historySummary } from "../overview";
import type { ScorePoint } from "../types";

const WIDTH = 168;
const HEIGHT = 44;

/**
 * Score history as a small line on a fixed 0 to 100 scale. The line is a picture of the numbers, so the
 * same numbers are always available as text: an image description and an expandable table.
 */
export default function ScoreTrend({ history }: { history: ScorePoint[] }) {
  const scores = history.map((p) => p.score);
  if (scores.length < 2)
    return <p className="muted small">{historySummary(scores)}</p>;
  const points = chartPoints(scores, WIDTH, HEIGHT);
  const last = points[points.length - 1]!;
  return (
    <div className="trend">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width={WIDTH}
        height={HEIGHT}
        role="img"
        aria-label={historySummary(scores)}
        className="trend-svg"
      >
        <line
          x1="0"
          x2={WIDTH}
          y1={HEIGHT - 4}
          y2={HEIGHT - 4}
          className="trend-base"
        />
        <polyline
          points={points.map((p) => `${p.x},${p.y}`).join(" ")}
          className="trend-line"
          fill="none"
        />
        {points.slice(0, -1).map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="2" className="trend-dot" />
        ))}
        <circle cx={last.x} cy={last.y} r="3.5" className="trend-last" />
      </svg>
      <details className="trend-table">
        <summary className="small">Score history</summary>
        <table className="small">
          <caption className="visually-hidden">
            Score of each completed scan, oldest first
          </caption>
          <thead>
            <tr>
              <th scope="col">Scanned</th>
              <th scope="col">Score</th>
            </tr>
          </thead>
          <tbody>
            {history.map((p) => (
              <tr key={p.scan_id}>
                <td>{formatDate(p.scanned_at)}</td>
                <td>{p.score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
