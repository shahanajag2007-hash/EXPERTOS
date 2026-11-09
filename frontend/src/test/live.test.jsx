import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LiveConsultationRoom, { UNLOCK_NOTICE } from "../components/LiveConsultation/LiveConsultationRoom";
import { jsonResponse, mockFetch, sse, sseResponse } from "./helpers";

const CONSULTATION = { id: "c-1", token: "tok" };
const PARTICIPANTS = [
  { key: "Database Engineer", name: "Alex Morgan", first_name: "Alex", role: "Senior Database Engineer", emoji: "🗄" },
  { key: "Security Expert", name: "Sarah Patel", first_name: "Sarah", role: "Cyber Security Consultant", emoji: "🛡" },
];
const AGENDA = [{ key: "review", label: "Reviewing the project" }, { key: "trade_offs", label: "Discussing trade-offs" }];

function session(overrides = {}) {
  const stage = overrides.stage ?? 0;
  const complete = stage >= AGENDA.length;
  const status = overrides.status || "active";
  return {
    id: "s-1", consultation_id: "c-1", status, busy: false, rounds: 0, max_rounds: 40,
    phase: status !== "active" ? "closed" : complete ? "user_interaction" : "expert_discussion",
    can_message: status === "active" && complete,
    stage, agenda: AGENDA, current_stage_label: complete ? null : AGENDA[stage].label, agenda_complete: complete,
    stage_speakers_needed: 2, stage_speakers_done: 0,
    participants: PARTICIPANTS, problem: "A yoga booking SaaS", messages: [], summary: null,
    summary_error: null, ...overrides,
  };
}

const msg = (id, seq, role, content, expert_key = null, agenda_stage = null) =>
  ({ id, seq, role, content, expert_key, agenda_stage });

const STAGE_ONE = [
  msg(1, 1, "expert", "Indexes will help reads but watch write overhead.", "Database Engineer", 0),
  msg(2, 2, "expert", "I agree with Alex, but access rules must not leak data.", "Security Expert", 0),
];
const STAGE_TWO = [
  msg(3, 3, "expert", "The trade-off is cost versus consistency.", "Database Engineer", 1),
  msg(4, 4, "expert", "Then we lock down tenant isolation first.", "Security Expert", 1),
];

function roundFor(messages, before, stage) {
  return sseResponse([
    sse("turn_start", { expert_key: messages[0].expert_key }),
    sse("token", { expert_key: messages[0].expert_key, text: messages[0].content }),
    sse("message", messages[0]),
    sse("turn_start", { expert_key: messages[1].expert_key }),
    sse("message", messages[1]),
    sse("round_done", session({ messages: [...before, ...messages], stage })),
  ]);
}

const input = () => screen.getByLabelText("Message the experts");
const send = () => screen.getByRole("button", { name: "Send" });

describe("Live consultation room", () => {
  it("runs the whole agenda automatically, with the message box locked, then unlocks it", async () => {
    let calls = 0;
    mockFetch({
      "POST /live/sessions": jsonResponse(session()),
      "POST /live/sessions/s-1/rounds": () => {
        calls += 1;
        return calls === 1 ? roundFor(STAGE_ONE, [], 1) : roundFor(STAGE_TWO, STAGE_ONE, 2);
      },
    });
    render(<LiveConsultationRoom consultation={CONSULTATION} onHide={() => {}} />);

    expect(await screen.findByText("Indexes will help reads but watch write overhead.")).toBeInTheDocument();
    expect(input()).toBeDisabled();
    expect(send()).toBeDisabled();
    expect(screen.getByText(/You can send messages once they finish/)).toBeInTheDocument();

    // Stage two runs without any click.
    expect(await screen.findByText("Then we lock down tenant isolation first.", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(await screen.findByText(UNLOCK_NOTICE)).toBeInTheDocument();
    expect(UNLOCK_NOTICE).toBe("You can discuss your queries and interact with the experts now.");
    await waitFor(() => expect(input()).toBeEnabled());
    expect(screen.getByText("Waiting for you")).toBeInTheDocument();
    expect(screen.getAllByText("✓")).toHaveLength(2);

    // The agenda is done, so no further automatic rounds are requested.
    await new Promise((r) => setTimeout(r, 400));
    expect(calls).toBe(2);
  });

  it("keeps the message box locked while the panel is discussing, even when idle", async () => {
    mockFetch({
      "POST /live/sessions": jsonResponse(session({ messages: STAGE_ONE, stage: 1, busy: true })),
      "GET /live/sessions/s-1": jsonResponse(session({ messages: STAGE_ONE, stage: 1, busy: true })),
    });
    render(<LiveConsultationRoom consultation={CONSULTATION} onHide={() => {}} />);
    await screen.findByText(/I agree with Alex/);
    await userEvent.type(input(), "Can I interrupt?");
    expect(input()).toHaveValue("");
    expect(send()).toBeDisabled();
  });

  it("sends the client's question with an idempotency ID and shows the reply in order", async () => {
    const opening = [...STAGE_ONE, ...STAGE_TWO];
    const reply = msg(6, 6, "expert", "Postgres row locks prevent double bookings.", "Database Engineer");
    const question = msg(5, 5, "client", "How do we stop double bookings?");
    mockFetch({
      "POST /live/sessions": jsonResponse(session({ messages: opening, stage: 2 })),
      "POST /live/sessions/s-1/rounds": (url, options) => {
        const body = JSON.parse(options.body);
        expect(body.message).toBe("How do we stop double bookings?");
        expect(body.message_id).toBeTruthy();
        return sseResponse([
          sse("message", question),
          sse("turn_start", { expert_key: "Database Engineer" }),
          sse("message", reply),
          sse("turn_skipped", { expert_key: "Security Expert" }),
          sse("round_done", session({ messages: [...opening, question, reply], rounds: 1, stage: 2 })),
        ]);
      },
    });
    render(<LiveConsultationRoom consultation={CONSULTATION} onHide={() => {}} />);

    await screen.findByText(UNLOCK_NOTICE);
    await userEvent.type(input(), "How do we stop double bookings?{Enter}");

    expect(await screen.findByText("Postgres row locks prevent double bookings.")).toBeInTheDocument();
    expect(screen.getByText("Sarah had nothing to add")).toBeInTheDocument();
    const texts = screen.getAllByText(/double bookings|tenant isolation|discuss your queries/).map((n) => n.textContent);
    expect(texts.indexOf(UNLOCK_NOTICE)).toBeLessThan(texts.indexOf("How do we stop double bookings?"));
    expect(texts.indexOf("How do we stop double bookings?")).toBeLessThan(
      texts.indexOf("Postgres row locks prevent double bookings."),
    );
  });

  it("pauses the automatic discussion with a retry when a round fails", async () => {
    let calls = 0;
    mockFetch({
      "POST /live/sessions": jsonResponse(session({ messages: STAGE_ONE, stage: 1 })),
      "POST /live/sessions/s-1/rounds": () => {
        calls += 1;
        return calls === 1
          ? sseResponse([sse("error", { error: "The AI models are busy right now.", code: "rate_limit", retryable: true })])
          : roundFor(STAGE_TWO, STAGE_ONE, 2);
      },
      "GET /live/sessions/s-1": jsonResponse(session({ messages: STAGE_ONE, stage: 1 })),
    });
    render(<LiveConsultationRoom consultation={CONSULTATION} onHide={() => {}} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("busy");
    expect(screen.getByText("The discussion is paused")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 400));
    expect(calls).toBe(1);            // not retried in a loop

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(UNLOCK_NOTICE)).toBeInTheDocument();
  });

  it("pauses when no expert manages to speak in an agenda round", async () => {
    mockFetch({
      "POST /live/sessions": jsonResponse(session()),
      "POST /live/sessions/s-1/rounds": sseResponse([
        sse("turn_start", { expert_key: "Database Engineer" }),
        sse("turn_error", { expert_key: "Database Engineer", error: "The AI models are busy right now.", code: "rate_limit" }),
        sse("round_done", session()),
      ]),
    });
    render(<LiveConsultationRoom consultation={CONSULTATION} onHide={() => {}} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The experts couldn't continue the discussion");
    expect(input()).toBeDisabled();
  });

  it("ends the session and turns the room into the Key Takeaways", async () => {
    const opening = [...STAGE_ONE, ...STAGE_TWO];
    const summary = {
      project_understanding: "A booking SaaS for yoga studios.", main_problems: ["Double bookings"],
      expert_insights: [{ expert: "Alex", insight: "Use row-level locks" }],
      agreements: ["Use Postgres"], disagreements: ["Caching timing: Alex later, Sarah now; resolved: later"],
      decisions: ["Postgres as the main store"], risks: ["Tenant data leaks"],
      recommended_solution: "Modular monolith on Postgres.", next_steps: ["Model the schema", "Add row locks"],
      unanswered_questions: ["Expected peak load?"], conclusion: "Proceed with the monolith.",
      agenda_completed: 2, agenda_total: 2,
    };
    mockFetch({
      "POST /live/sessions": jsonResponse(session({ messages: opening, stage: 2 })),
      "POST /live/sessions/s-1/close": jsonResponse(session({ messages: opening, stage: 2, status: "closed", summary })),
    });
    render(<LiveConsultationRoom consultation={CONSULTATION} onHide={() => {}} />);
    await screen.findByText(UNLOCK_NOTICE);

    await userEvent.click(screen.getByRole("button", { name: "End & Summarize" }));
    expect(await screen.findByRole("heading", { name: "Key Takeaways from the Live Discussion" })).toBeInTheDocument();
    for (const heading of ["Main problems identified", "Important insights from each expert", "Points of agreement",
      "Key disagreements and how they were resolved", "Important decisions", "Final recommendation",
      "Actionable next steps", "Potential risks", "Unresolved questions", "Final consolidated conclusion"]) {
      expect(screen.getByText(heading)).toBeInTheDocument();
    }
    expect(screen.getByText("Use row-level locks")).toBeInTheDocument();
    expect(screen.queryByLabelText("Message the experts")).not.toBeInTheDocument();
    expect(screen.queryByText(/ended after/)).not.toBeInTheDocument();

    // The transcript is preserved, not discarded.
    await userEvent.click(screen.getByRole("button", { name: "Show full transcript" }));
    expect(screen.getByText(/Indexes will help reads/)).toBeInTheDocument();
  });

  it("restores a finished discussion and its takeaways after a refresh, without new rounds", async () => {
    const summary = { project_understanding: "x", conclusion: "Stopped early.", main_problems: [],
                      agenda_completed: 1, agenda_total: 2 };
    const { calls } = mockFetch({
      "POST /live/sessions": jsonResponse(session({ messages: STAGE_ONE, stage: 1, status: "closed", summary })),
    });
    render(<LiveConsultationRoom consultation={CONSULTATION} onHide={() => {}} />);
    expect(await screen.findByText("Stopped early.")).toBeInTheDocument();
    expect(screen.getByText(/ended after 1 of 2 agenda items/)).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 400));
    expect(calls.some((c) => c.key.includes("/rounds"))).toBe(false);
  });

  it("still shows summaries saved in the earlier format", async () => {
    const summary = { project_understanding: "Old", strengths: ["Clear scope"], weaknesses: ["No tests"],
                      conclusion: "Old conclusion." };
    mockFetch({
      "POST /live/sessions": jsonResponse(session({ messages: STAGE_ONE, stage: 2, status: "closed", summary })),
    });
    render(<LiveConsultationRoom consultation={CONSULTATION} onHide={() => {}} />);
    expect(await screen.findByText("Main strengths")).toBeInTheDocument();
    expect(screen.getByText("No tests")).toBeInTheDocument();
  });
});
