import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar/Navbar";
import { IMAGE_ACCEPT, useFileUploads } from "../services/files";
import { ChooseFilesButton, FileList } from "../components/FileUpload/FileList";

function DesignAdvisor() {
  const navigate = useNavigate();

  const [figmaLink, setFigmaLink] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const screenshots = useFileUploads({ accept: IMAGE_ACCEPT });

  function reviewDesign() {
    if (screenshots.uploading) {
      setError("Wait for your screenshots to finish uploading.");
      return;
    }
    if (!notes.trim() && !screenshots.ids.length) {
      setError("Describe the design you'd like Maya to review, or upload a screenshot.");
      return;
    }

    const description = notes.trim() || "Please review the attached screenshot(s) of my design.";
    const problem = figmaLink.trim()
      ? `${description}\n\nFigma link (for reference): ${figmaLink.trim()}`
      : description;

    // Maya's Expert Room runs the actual consultation; uploaded screenshots go with it.
    navigate("/expert/maya", { state: { problem, files: screenshots.done } });
  }

  return (
    <>
      <Navbar />

      <div className="min-h-screen bg-slate-50 px-4 sm:px-6 py-10 sm:py-16">

      <div className="bg-white rounded-3xl shadow-xl p-6 sm:p-12 max-w-5xl w-full mx-auto">

        <p className="text-purple-600 font-semibold uppercase tracking-widest">
          Design Advisor
        </p>

        <h1 className="text-4xl sm:text-5xl font-bold mt-4">
          Maya Chen
        </h1>

        <p className="text-gray-500 mt-4 text-lg">
          Describe your design or share a Figma link to receive professional UI/UX feedback.
        </p>

        <div className="grid md:grid-cols-2 gap-8 mt-10">

          <div>

            <div
              className="border-2 border-dashed rounded-3xl h-48 sm:h-56 flex flex-col items-center justify-center text-center text-gray-400 px-6"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                screenshots.add(e.dataTransfer.files);
              }}
            >

              <span>📷 Upload Screenshot</span>

              <ChooseFilesButton
                uploads={screenshots}
                accept={IMAGE_ACCEPT}
                label="Choose screenshots"
                className="mt-3 text-sm border border-slate-300 hover:bg-slate-50 text-gray-600 rounded-full px-4 py-1 transition"
              />

              <span className="mt-2 text-xs">PNG, JPEG, WebP or GIF, up to 10 MB. Or drop them here.</span>

            </div>

            <FileList uploads={screenshots} />

            <textarea
              rows={5}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              aria-label="Design description"
              className="w-full mt-6 border rounded-2xl px-5 py-4 resize-none focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="What are you designing, who is it for, and what feels off? e.g. 'Our signup flow has a high drop-off on step 2...'"
            />

            <input
              value={figmaLink}
              onChange={(e) => setFigmaLink(e.target.value)}
              aria-label="Figma link"
              className="w-full mt-4 border rounded-2xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="Paste Figma Link (optional)"
            />

            <p className="text-xs text-gray-500 mt-2">
              Maya can't open links directly, so include the key details in your description.
            </p>

            {error && (
              <p className="mt-4 text-red-600 text-sm" role="alert">
                {error}
              </p>
            )}

            <button
              onClick={reviewDesign}
              className="mt-6 bg-purple-600 hover:bg-purple-700 text-white px-8 py-4 rounded-2xl"
            >
              Review Design →
            </button>

          </div>

          <div className="bg-slate-50 rounded-3xl p-6 sm:p-8">

            <h2 className="text-2xl font-bold">
              Review Preview
            </h2>

            <div className="mt-8 space-y-5">

              <div>🎨 Visual Hierarchy</div>

              <div>📱 Responsive Layout</div>

              <div>♿ Accessibility</div>

              <div>🎯 User Experience</div>

              <div>✨ Design Consistency</div>

            </div>

          </div>

        </div>

      </div>

      </div>

    </>
  );
}

export default DesignAdvisor;
