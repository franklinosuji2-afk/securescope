import { useState } from "react";
import { createPdfReport } from "../api";
import { ErrorNotice } from "./ui";

/** Asks the server for the PDF report of a finished scan, then downloads it through the short-lived link the
 * server returns. The report is made once and kept; the link only works for the person who asked. */
export default function PdfReportButton({
  scanId,
  host,
}: {
  scanId: string;
  host?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const link = await createPdfReport(scanId);
      // The browser saves the file; the page stays where it is.
      window.location.assign(link.url);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "The report could not be created.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="btn-ghost"
        disabled={busy}
        onClick={() => void download()}
        aria-label={
          host ? `Download PDF report for ${host}` : "Download PDF report"
        }
      >
        {busy ? "Preparing PDF…" : "PDF"}
      </button>
      {error && <ErrorNotice message={error} />}
    </>
  );
}
