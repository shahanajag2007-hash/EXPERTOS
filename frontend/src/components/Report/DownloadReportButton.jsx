import { downloadReport } from "../../services/reportExport";

/** Secondary-style button that downloads a report built by `build()` as Markdown. */
function DownloadReportButton({ build, label = "Download report", className = "" }) {
  return (
    <button
      type="button"
      onClick={() => downloadReport(build())}
      className={className || "border border-slate-300 hover:bg-slate-50 px-5 py-2 rounded-full text-sm font-medium transition"}
      title="Download as a Markdown (.md) file"
    >
      ⬇ {label}
    </button>
  );
}

export default DownloadReportButton;
