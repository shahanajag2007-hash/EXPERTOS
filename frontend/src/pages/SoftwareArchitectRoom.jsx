import { useState } from "react";
import Navbar from "../components/Navbar/Navbar";

function SoftwareArchitectRoom() {

  const [step, setStep] = useState(1);

  return (

    <>

      <Navbar />

      <div className="min-h-screen bg-gradient-to-br from-slate-100 via-indigo-50 to-blue-100">

        <div className="max-w-7xl mx-auto px-8 py-10">

          {/* Expert Header */}

          <div className="bg-white rounded-[36px] shadow-xl border border-slate-200 overflow-hidden">

            <div className="bg-gradient-to-r from-indigo-700 via-indigo-600 to-blue-600 h-3"></div>

            <div className="p-10">

              <div className="flex justify-between items-start">

                <div className="flex gap-8">

                  <div className="w-28 h-28 rounded-full bg-gradient-to-br from-indigo-600 to-blue-700 text-white flex items-center justify-center text-6xl shadow-lg">

                    👨‍💻

                  </div>

                  <div>

                    <div className="inline-flex items-center gap-3 bg-green-100 text-green-700 px-5 py-2 rounded-full font-semibold">

                      <span className="w-3 h-3 rounded-full bg-green-500 animate-pulse"></span>

                      Available Now

                    </div>

                    <h1 className="text-5xl font-bold mt-6">

                      Ethan Walker

                    </h1>

                    <p className="text-indigo-600 text-xl mt-2">

                      Senior Software Architect

                    </p>

                    <p className="text-gray-500 leading-8 mt-6 max-w-3xl">

                      Designing scalable software is not about choosing
                      the newest technology.

                      It's about choosing the right architecture for
                      today's requirements while preparing for tomorrow.

                    </p>

                  </div>

                </div>

                <div className="text-right">

                  <div className="text-5xl font-bold text-indigo-600">

                    ⭐ 4.9

                  </div>

                  <p className="mt-4 text-gray-500">

                    12+ Years Experience

                  </p>

                  <p className="text-gray-400">

                    2,847 Consultations

                  </p>

                </div>

              </div>

            </div>

          </div>

          {/* Progress */}

          <div className="bg-white rounded-3xl shadow mt-8 p-8">

            <div className="flex justify-between items-center">

              {[
                "Project",
                "Context",
                "Goals",
                "Analysis",
                "Discussion"
              ].map((item, index) => (

                <div
                  key={item}
                  className="flex flex-col items-center flex-1"
                >

                  <div
                    className={`w-12 h-12 rounded-full flex items-center justify-center font-bold ${
                      step >= index + 1
                        ? "bg-indigo-600 text-white"
                        : "bg-gray-200"
                    }`}
                  >

                    {index + 1}

                  </div>

                  <p className="mt-3 font-medium">

                    {item}

                  </p>

                </div>

              ))}

            </div>

          </div>

          {/* Main Layout */}

          <div className="grid lg:grid-cols-3 gap-8 mt-8">

            {/* Left Side */}

            <div className="lg:col-span-2">

              <div className="bg-white rounded-[32px] shadow-xl border border-slate-200 overflow-hidden">

                <div className="px-8 py-6 border-b bg-slate-50">

                  <h2 className="text-3xl font-bold">

                    📝 Project Consultation

                  </h2>

                  <p className="text-gray-500 mt-2">

                    Ethan will first understand your project before
                    preparing his recommendation.

                  </p>

                </div>

                <div className="p-8">
                                      {step === 1 && (

                    <div className="space-y-8">

                      <div>

                        <label className="font-semibold text-gray-700">

                          Project Name

                        </label>

                        <input
                          className="w-full mt-3 border rounded-2xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          placeholder="Example: ExpertOS"
                        />

                      </div>

                      <div>

                        <label className="font-semibold text-gray-700">

                          Describe your project

                        </label>

                        <textarea
                          rows={7}
                          className="w-full mt-3 border rounded-2xl px-5 py-4 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          placeholder="Explain what you're building..."
                        />

                      </div>

                      <div className="flex justify-end">

                        <button
                          onClick={() => setStep(2)}
                          className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-4 rounded-2xl font-semibold"
                        >

                          Continue →

                        </button>

                      </div>

                    </div>

                  )}

                  {step === 2 && (

                    <div className="space-y-8">

                      <div>

                        <label className="font-semibold text-gray-700">

                          Current Tech Stack

                        </label>

                        <input
                          className="w-full mt-3 border rounded-2xl px-5 py-4"
                          placeholder="React, Flask, PostgreSQL..."
                        />

                      </div>

                      <div>

                        <label className="font-semibold text-gray-700">

                          Current Challenges

                        </label>

                        <textarea
                          rows={6}
                          className="w-full mt-3 border rounded-2xl px-5 py-4 resize-none"
                          placeholder="Performance, architecture, scalability..."
                        />

                      </div>

                      <div className="flex justify-between">

                        <button
                          onClick={() => setStep(1)}
                          className="border px-8 py-4 rounded-2xl"
                        >

                          ← Back

                        </button>

                        <button
                          onClick={() => setStep(3)}
                          className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-4 rounded-2xl"
                        >

                          Continue →

                        </button>

                      </div>

                    </div>

                  )}

                  {step === 3 && (

                    <div className="space-y-8">

                      <div>

                        <label className="font-semibold text-gray-700">

                          Goals

                        </label>

                        <textarea
                          rows={5}
                          className="w-full mt-3 border rounded-2xl px-5 py-4 resize-none"
                          placeholder="What do you want to achieve?"
                        />

                      </div>

                      <div>

                        <label className="font-semibold text-gray-700">

                          Constraints

                        </label>

                        <textarea
                          rows={5}
                          className="w-full mt-3 border rounded-2xl px-5 py-4 resize-none"
                          placeholder="Budget, timeline, team size..."
                        />

                      </div>

                      <div className="flex justify-between">

                        <button
                          onClick={() => setStep(2)}
                          className="border px-8 py-4 rounded-2xl"
                        >

                          ← Back

                        </button>

                        <button
                          onClick={() => setStep(4)}
                          className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-4 rounded-2xl"
                        >

                          Analyze Project →

                        </button>

                      </div>

                    </div>

                  )}

                  {step === 4 && (

                    <div className="text-center py-20">

                      <div className="text-6xl animate-pulse">

                        🧠

                      </div>

                      <h2 className="text-3xl font-bold mt-8">

                        Ethan is analyzing your project...

                      </h2>

                      <p className="text-gray-500 mt-5 max-w-xl mx-auto">

                        Reviewing architecture, scalability,
                        technology choices and long-term maintainability.

                      </p>

                      <button
                        onClick={() => setStep(5)}
                        className="mt-10 bg-indigo-600 hover:bg-indigo-700 text-white px-10 py-4 rounded-2xl"
                      >

                        Skip Demo →

                      </button>

                    </div>

                  )}

                  {step === 5 && (
                                      <div className="space-y-8">

                    <div className="bg-gradient-to-r from-indigo-600 to-blue-700 rounded-3xl text-white p-8">

                      <p className="uppercase tracking-widest text-indigo-200">

                        Primary Recommendation

                      </p>

                      <h2 className="text-4xl font-bold mt-4">

                        Start with a Modular Monolith

                      </h2>

                      <p className="leading-8 mt-6 text-lg">

                        Based on your current team size, expected traffic and
                        development stage, a modular monolith will reduce
                        complexity while keeping the project scalable.

                      </p>

                    </div>

                    <div className="grid md:grid-cols-2 gap-6">

                      <div className="bg-slate-50 rounded-3xl p-6">

                        <h3 className="font-bold text-xl">

                          ✅ Why this recommendation?

                        </h3>

                        <p className="text-gray-600 mt-4 leading-7">

                          Your architecture doesn't yet require the operational
                          overhead of distributed microservices.

                          Starting modular lets you scale naturally.

                        </p>

                      </div>

                      <div className="bg-slate-50 rounded-3xl p-6">

                        <h3 className="font-bold text-xl">

                          🔄 Alternative

                        </h3>

                        <p className="text-gray-600 mt-4 leading-7">

                          If multiple teams will work independently within the
                          next year, consider moving towards microservices
                          gradually.

                        </p>

                      </div>

                    </div>

                    <div className="bg-white border rounded-3xl p-8">

                      <h2 className="text-3xl font-bold">

                        💬 Continue Discussion with Ethan

                      </h2>

                      <p className="text-gray-500 mt-3">

                        Your report is ready.

                        Ask Ethan anything about the recommendations,
                        trade-offs or implementation.

                      </p>

                      <div className="mt-8 bg-slate-50 rounded-3xl h-[260px] flex items-center justify-center">

                        <div className="text-center">

                          <div className="text-6xl">

                            💬

                          </div>

                          <p className="mt-5 text-gray-500">

                            Your existing chatbot from Phase 5
                            will appear here.

                          </p>

                        </div>

                      </div>

                    </div>

                  </div>

                  )}

                </div>

              </div>

            </div>

            {/* Right Sidebar */}

            <div className="space-y-6">

              <div className="bg-white rounded-3xl shadow-xl border border-slate-200 p-8 sticky top-28">

                <h2 className="text-2xl font-bold">

                  👨‍💻 Ethan Walker

                </h2>

                <p className="text-indigo-600 mt-2">

                  Senior Software Architect

                </p>

                <div className="space-y-4 mt-8">

                  <div className="flex justify-between">

                    <span>Experience</span>

                    <strong>12+ Years</strong>

                  </div>

                  <div className="flex justify-between">

                    <span>Projects</span>

                    <strong>840+</strong>

                  </div>

                  <div className="flex justify-between">

                    <span>Consultations</span>

                    <strong>2,847</strong>

                  </div>

                  <div className="flex justify-between">

                    <span>Rating</span>

                    <strong>⭐ 4.9</strong>

                  </div>

                </div>

                <hr className="my-8"/>

                <h3 className="font-bold">

                  Expertise

                </h3>

                <div className="flex flex-wrap gap-2 mt-5">

                  {[
                    "Architecture",
                    "Scalability",
                    "REST APIs",
                    "Cloud",
                    "Backend"
                  ].map((item) => (

                    <span
                      key={item}
                      className="bg-indigo-100 text-indigo-700 px-3 py-2 rounded-full text-sm"
                    >

                      {item}

                    </span>

                  ))}

                </div>

                <hr className="my-8"/>

                <h3 className="font-bold">

                  Recent Consultations

                </h3>

                <div className="space-y-3 mt-5">

                  <div className="bg-slate-50 rounded-xl p-4">

                    LMS Platform Review

                  </div>

                  <div className="bg-slate-50 rounded-xl p-4">

                    FinTech API Architecture

                  </div>

                  <div className="bg-slate-50 rounded-xl p-4">

                    SaaS Scaling Strategy

                  </div>

                </div>

              </div>

            </div>

          </div>

        </div>

      </div>

    </>

  );

}

export default SoftwareArchitectRoom;