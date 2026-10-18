import type { SetupStep } from "../overview";

const MARK: Record<SetupStep["state"], string> = { done: "✓", current: "→", waiting: "" };
const STATE_TEXT: Record<SetupStep["state"], string> = { done: "Done", current: "Next step", waiting: "Later" };

/** The path from a new account to a first useful result. Shown until a first scan has completed. */
export default function SetupGuide({ steps }: { steps: SetupStep[] }) {
  return (
    <section className="card guide" aria-labelledby="guide-title">
      <h2 id="guide-title">Get your first result</h2>
      <p className="muted small">No scan yet. Results appear here only after a real scan has run.</p>
      <ol className="guide-steps">
        {steps.map((step, i) => (
          <li key={step.id} className={`guide-step guide-${step.state}`} aria-current={step.state === "current" ? "step" : undefined}>
            <span className="guide-mark" aria-hidden="true">
              {MARK[step.state] || i + 1}
            </span>
            <div className="guide-body">
              <h3>
                {step.title} <span className="visually-hidden">({STATE_TEXT[step.state]})</span>
              </h3>
              {step.state !== "done" && <p className="muted small">{step.detail}</p>}
              {step.state === "current" && step.action && (
                <a className="btn btn-link" href={step.action.href}>
                  {step.action.label}
                </a>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
