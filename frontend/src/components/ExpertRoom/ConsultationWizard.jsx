import { useEffect, useState } from "react";

import { loadDiscovery } from "../../services/expertDiscovery";
import { DOCUMENT_ACCEPT } from "../../services/files";
import { ChooseFilesButton, FileList } from "../FileUpload/FileList";

// `uploads` (from useFileUploads) holds the project files; the parent keeps it
// so files survive moving between wizard steps and revising answers.
function ConsultationWizard({
    expert,
    initialAnswers = {},
    onReview,
    uploads = null
}) {

  const [step, setStep] = useState(1);
  const [steps, setSteps] = useState([]);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [validationError, setValidationError] = useState("");

  const [form, setForm] = useState(initialAnswers);
  useEffect(() => {

      let cancelled = false;

      async function initialize() {
          setLoading(true);
          setLoadError("");
          try {

              const data = await loadDiscovery(expert);

              if (!cancelled) setSteps(data);

          }

          catch (e) {

              if (!cancelled) setLoadError(e.message);

          }

          if (!cancelled) setLoading(false);

      }

      initialize();

      return () => {
          cancelled = true;
      };

  }, [expert, attempt]);
  const currentStep = steps[step - 1];

  function updateField(name, value) {

    setForm((prev) => ({

      ...prev,

      [name]: value

    }));

  }

  function continueFromProject() {

    if (!form.description?.trim()) {
      setValidationError(`Please describe your project so ${expert.name.split(" ")[0]} has something to review.`);
      return;
    }

    setValidationError("");
    setStep(2);

  }
  return (

    <div className="bg-white rounded-[32px] border border-slate-200 shadow-sm overflow-hidden">

      <div className="px-6 sm:px-8 py-6 border-b bg-slate-50">

        <h2 className="text-2xl sm:text-3xl font-bold">

          🔍 Discovery Session

        </h2>

        <p className="text-gray-500 mt-2">

          Answer a few questions so {expert.name.split(" ")[0]} can understand your project before preparing a personalized recommendation.
        </p>

      </div>

      <div className="p-6 sm:p-8 min-h-[480px] sm:min-h-[620px] flex flex-col">
        {!loading && loadError && (

        <div className="flex-1 flex items-center justify-center">

        <div className="text-center max-w-md">

        <div className="text-5xl">⚠️</div>

        <h2 className="text-2xl font-bold mt-6">

        Couldn't load the discovery session

        </h2>

        <p className="text-gray-500 mt-3 leading-7">

        {loadError}

        </p>

        <button

        onClick={() => setAttempt((n) => n + 1)}

        className="mt-8 bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-3 rounded-2xl font-semibold"

        >

        Try Again

        </button>

        </div>

        </div>

        )}

        {loading && (

        <div className="flex-1 flex items-center justify-center">

        <div className="text-center">

        <div className="text-6xl">

        🧠

        </div>

        <h2 className="text-3xl font-bold mt-6">

        Loading Discovery Session...

        </h2>

        </div>

        </div>

        )}

        {!loading && !loadError && (
        <>
        {/* Progress */}

        <div className="flex justify-between mb-10">

          {steps.map((item, index) => (

            <div
              key={item.title}
              className="flex flex-col items-center flex-1"
            >

              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold ${
                  step >= index + 1
                    ? "bg-indigo-600 text-white"
                    : "bg-gray-200 text-gray-500"
                }`}
              >

                {index + 1}

              </div>

              <span className="mt-2 text-xs sm:text-sm text-center">

                {item.title}

              </span>

            </div>

          ))}

        </div>

        {step === 1 && currentStep && (

<div className="space-y-8 flex-1">

<div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-5">

<p className="text-indigo-700 font-semibold">

👋 Welcome! Before reviewing your project, I'd like to understand what you're building.

</p>

<p className="text-gray-600 mt-2 leading-7">

{expert.greeting}

</p>

</div>

{currentStep.fields.map((field) => (

<div key={field.name}>

<label htmlFor={`wizard-${field.name}`} className="block font-semibold mb-2">

{field.label}

</label>

{field.name === "description" ? (

<textarea

id={`wizard-${field.name}`}


rows={7}

className="w-full border rounded-2xl px-5 py-4 resize-none"

placeholder={field.placeholder}

value={form[field.name] || ""}

onChange={(e) =>

updateField(

field.name,

e.target.value

)

}

/>

) : (

<input

id={`wizard-${field.name}`}


className="w-full border rounded-2xl px-5 py-4"

placeholder={field.placeholder}

value={form[field.name] || ""}

onChange={(e) =>

updateField(

field.name,

e.target.value

)

}

/>

)}

</div>

))}

{validationError && (

<p className="text-red-600 text-sm" role="alert">

{validationError}

</p>

)}

<div className="flex justify-end">

<button

onClick={continueFromProject}

className="bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 text-white px-10 py-4 rounded-2xl font-semibold shadow-lg"

>

Continue Discovery →

</button>

</div>

</div>

)}

        {step === 2 && currentStep && (

        <div className="space-y-6 flex-1">

        {currentStep.fields.map((field) => (

        <div key={field.name}>

        <label htmlFor={`wizard-${field.name}`} className="block font-semibold mb-2">

        {field.label}

        </label>

        {field.name === "context" ||
        field.name === "deployment" ||
        field.name === "security" ||
        field.name === "problems" ? (

        <textarea

id={`wizard-${field.name}`}


        rows={6}

        className="w-full border rounded-2xl px-5 py-4 resize-none"

        placeholder={field.placeholder}

        value={form[field.name] || ""}

        onChange={(e)=>

        updateField(field.name,e.target.value)

        }

        />

        ) : (

        <input

id={`wizard-${field.name}`}


        className="w-full border rounded-2xl px-5 py-4"

        placeholder={field.placeholder}

        value={form[field.name] || ""}

        onChange={(e)=>

        updateField(field.name,e.target.value)

        }

        />

        )}

        </div>

        ))}

        <div
          className="border-2 border-dashed border-slate-300 rounded-2xl p-8 text-center"
          onDragOver={(e) => {
            if (uploads) e.preventDefault();
          }}
          onDrop={(e) => {
            if (!uploads) return;
            e.preventDefault();
            uploads.add(e.dataTransfer.files);
          }}
        >

        <div className="text-4xl">

        📂

        </div>

        <h3 className="font-semibold text-lg mt-3">

        Upload Project Files

        </h3>

        <p className="text-gray-500 mt-2">

        PRD, ZIP, PDF, Images or Documentation

        </p>

        {uploads && (

          <>

            <ChooseFilesButton uploads={uploads} accept={DOCUMENT_ACCEPT} />

            <p className="text-xs text-gray-400 mt-3">

            Drag files here or choose them. Up to 5 files, 10 MB each. {expert.name.split(" ")[0]} reads their text; images are reviewed by image-capable models.

            </p>

            <FileList uploads={uploads} />

          </>

        )}

        </div>

        <div className="flex justify-between">

        <button

        onClick={()=>setStep(1)}

        className="border px-8 py-4 rounded-2xl"

        >

        ← Back

        </button>

        <button

        onClick={()=>setStep(3)}

        className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-4 rounded-2xl"

        >

        Continue Discovery →

        </button>

        </div>

        </div>

        )}

        {step === 3 && currentStep && (

        <div className="space-y-6 flex-1">

        {currentStep.fields.map((field) => (

        <div key={field.name}>

        <label htmlFor={`wizard-${field.name}`} className="block font-semibold mb-2">

        {field.label}

        </label>

        <textarea

id={`wizard-${field.name}`}


        rows={5}

        className="w-full border rounded-2xl px-5 py-4 resize-none"

        placeholder={field.placeholder}

        value={form[field.name] || ""}

        onChange={(e)=>

        updateField(field.name, e.target.value)

        }

        />

        </div>

        ))}

        <div className="flex justify-between">

        <button

        onClick={() => setStep(2)}

        className="border px-8 py-4 rounded-2xl"

        >

        ← Back

        </button>

        <button

        onClick={() => onReview(form)}

        disabled={Boolean(uploads?.uploading)}

        className="bg-gradient-to-r from-indigo-600 to-blue-600 text-white px-10 py-4 rounded-2xl font-semibold shadow-lg disabled:opacity-60"

        >

        {uploads?.uploading ? "Uploading files…" : `Let ${expert.name.split(" ")[0]} Review →`}

        </button>

        </div>

        </div>

        )}

        </>

        )}
      </div>

    </div>

  );

}

export default ConsultationWizard;