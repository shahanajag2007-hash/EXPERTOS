import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { __resetStatsCache } from "../hooks/useStats";
import { saveSession } from "../services/identity";
import { consultationReport, expertRoomReport } from "../services/reportExport";
import { EMPTY_STATS, jsonResponse, mockFetch, sse, sseResponse } from "./helpers";

function renderAt(entry) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <App />
    </MemoryRouter>,
  );
}

const ANALYSIS = {
  architecture: "Modular monolith.", tech_stack: "React and Flask.", database: "PostgreSQL.",
  security: "Use OAuth.", deployment: "Docker on a VM.", recommendation: "Start with the booking flow.",
};
const ARCHITECT = { name: "Ethan Walker", role: "Senior Software Architect", emoji: "👨‍💻" };

/** Fake XMLHttpRequest for uploads: answers with `respond(file)`. */
function mockUploads(respond) {
  const sent = [];
  class FakeXHR {
    constructor() {
      this.upload = {};
      this.headers = {};
    }
    open(method, url) {
      this.url = url;
    }
    setRequestHeader(k, v) {
      this.headers[k] = v;
    }
    send(form) {
      const file = form.get("files");
      sent.push({ file, headers: this.headers, conversationId: form.get("conversation_id") });
      setTimeout(() => {
        this.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 1 });
        const [status, body] = respond(file);
        this.status = status;
        this.responseText = JSON.stringify(body);
        this.onload();
      }, 0);
    }
    abort() {}
  }
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
  return sent;
}

describe("Accounts", () => {
  beforeEach(() => {
    __resetStatsCache();
  });

  it("creates an account, shows it in the navbar, and signs out", async () => {
    const { calls } = mockFetch({
      "GET /stats": jsonResponse(EMPTY_STATS),
      "POST /auth/register": jsonResponse({ token: "tok", user: { id: "u1", email: "ana@example.com", name: "Ana Lima" } }, 201),
      "POST /auth/logout": jsonResponse({ status: "signed_out" }),
    });
    const user = userEvent.setup();
    renderAt("/signin");

    await user.click(screen.getByRole("button", { name: "Create an account" }));
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Please enter a valid email address.")).toBeInTheDocument();
    expect(calls.some((c) => c.key === "POST /auth/register")).toBe(false);

    await user.type(screen.getByLabelText(/Name/), "Ana Lima");
    await user.type(screen.getByLabelText(/^Email/), "ana@example.com");
    await user.type(screen.getByLabelText(/Password/), "correct horse");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("heading", { name: "Choose Your AI Expert" })).toBeInTheDocument();
    const register = calls.find((c) => c.key === "POST /auth/register");
    expect(register.body).toEqual({ name: "Ana Lima", email: "ana@example.com", password: "correct horse" });
    expect(screen.getAllByText("Ana").length).toBeGreaterThan(0);

    // Later requests carry the session and the browser ID.
    const later = calls.at(-1).options.headers;
    expect(later.Authorization).toBe("Bearer tok");
    expect(later["X-Client-Id"]).toMatch(/^[a-f0-9]{48}$/);
  });

  it("shows the server's error for a wrong password", async () => {
    mockFetch({
      "GET /stats": jsonResponse(EMPTY_STATS),
      "POST /auth/login": jsonResponse({ error: "The email or password is incorrect.", code: "unauthorized" }, 401),
    });
    const user = userEvent.setup();
    renderAt("/signin");
    await user.type(screen.getByLabelText(/^Email/), "ana@example.com");
    await user.type(screen.getByLabelText(/Password/), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The email or password is incorrect.");
  });

  it("forgets an expired session", async () => {
    saveSession({ token: "old", user: { id: "u1", email: "a@example.com", name: "Ana" } });
    mockFetch({
      "GET /stats": jsonResponse(EMPTY_STATS),
      "GET /conversations": jsonResponse({ error: "Your session has expired.", code: "unauthorized" }, 401),
    });
    renderAt("/consultation");
    await waitFor(() => expect(localStorage.getItem("expertos.session")).toBeNull());
  });
});

describe("Start Consultation", () => {
  beforeEach(() => sessionStorage.clear());

  it("uploads a file, sends it with the analysis, and continues the saved conversation", async () => {
    const sent = mockUploads((file) => [201, { files: [{ id: "f1", filename: file.name, size_bytes: 12, kind: "document",
      content_type: "text/plain", characters: 12, note: null, conversation_id: null }] }]);
    const { calls } = mockFetch({
      "POST /analyze": jsonResponse({ expert: ARCHITECT, analysis: ANALYSIS, conversation_id: "c1",
                                      consultation: { id: "k1", token: "t1" } }),
      "POST /chat": jsonResponse({ switch: false, expert: ARCHITECT, reply: "Use Stripe.",
        history: [{ type: "chat", sender: "user", message: "Payments?" },
                  { type: "chat", sender: "expert", expert: ARCHITECT, message: "Use Stripe." }] }),
    });
    const user = userEvent.setup();
    renderAt("/consultation");

    const input = document.querySelector('input[type="file"]');
    await user.upload(input, new File(["requirements"], "brief.txt", { type: "text/plain" }));
    expect(await screen.findByText(/12 characters read/)).toBeInTheDocument();
    expect(sent[0].headers["X-Client-Id"]).toBeTruthy();

    await user.type(screen.getByLabelText("Project description"), "A booking app");
    await user.click(screen.getByRole("button", { name: "Start Consultation →" }));
    expect(await screen.findByText("Modular monolith.")).toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /analyze").body).toEqual({ prompt: "A booking app", file_ids: ["f1"] });
    expect(sessionStorage.getItem("expertos.active.consultation")).toBe("c1");

    await user.type(screen.getByPlaceholderText(/Ask/i), "Payments?");
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Use Stripe.")).toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /chat").body).toEqual({ conversation_id: "c1", message: "Payments?" });
  });

  it("shows the expert the backend switched to, and keeps them after a reload", async () => {
    const SARAH = { name: "Sarah Patel", role: "Cyber Security Consultant", emoji: "🛡", expertise: [] };
    sessionStorage.setItem("expertos.active.consultation", "c7");
    const history = [
      { type: "chat", sender: "user", message: "Can Sarah join?" },
      { type: "chat", sender: "expert", expert: ARCHITECT, message: "I'd like Sarah Patel to take over from here." },
      { type: "system", message: "🛡 Sarah Patel joined the consultation." },
      { type: "chat", sender: "expert", expert: SARAH, message: "Sarah here. Let's look at auth." },
    ];
    const { calls } = mockFetch({
      "GET /conversations/c7": jsonResponse({ id: "c7", kind: "quick_consultation", project: "Clinic app",
        report: ANALYSIS, expert: ARCHITECT, files: [], messages: [] }),
      "POST /chat": jsonResponse({ switch: true, expert: SARAH, reply: "Sarah here. Let's look at auth.", history }),
    });
    const user = userEvent.setup();
    const { unmount } = renderAt("/consultation");

    await user.type(await screen.findByPlaceholderText("Ask Ethan Walker anything about your project..."), "Can Sarah join?");
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Sarah here. Let's look at auth.")).toBeInTheDocument();
    expect(screen.getByText(/Sarah Patel joined the consultation/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Ask Sarah Patel anything about your project...")).toBeInTheDocument();
    expect(screen.getByText("Continue your consultation with Sarah Patel")).toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /chat").body).toEqual({ conversation_id: "c7", message: "Can Sarah join?" });

    // After a reload the backend's active expert (Sarah) is shown again.
    unmount();
    mockFetch({
      "GET /conversations/c7": jsonResponse({ id: "c7", kind: "quick_consultation", project: "Clinic app",
        report: ANALYSIS, expert: SARAH, files: [], messages: history }),
    });
    renderAt("/consultation");
    expect(await screen.findByPlaceholderText("Ask Sarah Patel anything about your project...")).toBeInTheDocument();
  });

  it("rejects unsupported files before uploading", async () => {
    const sent = mockUploads(() => [201, { files: [] }]);
    mockFetch({});
    const user = userEvent.setup({ applyAccept: false });
    renderAt("/consultation");
    await user.upload(document.querySelector('input[type="file"]'), new File(["MZ"], "setup.exe"));
    expect(await screen.findByText(/this file type isn't supported here/)).toBeInTheDocument();
    expect(sent).toHaveLength(0);
  });

  it("shows the server's reason when an upload is rejected, and removes files", async () => {
    mockUploads(() => [400, { error: "report.pdf is not a valid PDF file." }]);
    mockFetch({});
    const user = userEvent.setup();
    renderAt("/consultation");
    await user.upload(document.querySelector('input[type="file"]'), new File(["x"], "report.pdf"));
    expect(await screen.findByText("report.pdf is not a valid PDF file.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove report.pdf" }));
    expect(screen.queryByText("report.pdf is not a valid PDF file.")).not.toBeInTheDocument();
  });

  it("restores the open consultation after a reload", async () => {
    sessionStorage.setItem("expertos.active.consultation", "c9");
    mockFetch({
      "GET /conversations/c9": jsonResponse({
        id: "c9", kind: "quick_consultation", project: "Clinic app", report: ANALYSIS, expert: ARCHITECT, files: [],
        messages: [{ type: "chat", sender: "user", message: "Earlier question" },
                   { type: "chat", sender: "expert", expert: ARCHITECT, message: "Earlier answer" }],
      }),
    });
    renderAt("/consultation");
    expect(await screen.findByText("Earlier answer")).toBeInTheDocument();
    expect(screen.getByText("Modular monolith.")).toBeInTheDocument();
  });
});

describe("Expert Room history", () => {
  beforeEach(() => sessionStorage.clear());

  it("switches only the chatbot's role: the room stays Ethan's, and each room keeps its own identity", async () => {
    const report = { title: "Store plan", recommendation: "Modular monolith", description: "Because.", metrics: [] };
    const MAYA = { key: "Design Advisor", name: "Maya Chen", role: "Senior Product Designer", emoji: "🎨" };
    const ETHAN = { key: "Software Architect", name: "Ethan Walker", role: "Senior Software Architect", emoji: "👨‍💻" };
    let ethanActive = "Software Architect";
    let mayaActive = "Design Advisor";
    const ethanMessages = [];
    const conversation = (id, room, active, messages) => jsonResponse({
      id, kind: "expert_room", expert_key: room, answers: { description: "Clothing store" }, report, files: [],
      active_expert: active, messages,
    });
    sessionStorage.setItem("expertos.active.room.ethan", "r-ethan");
    sessionStorage.setItem("expertos.active.room.maya", "r-maya");
    const { calls } = mockFetch({
      "POST /expert/discovery": jsonResponse({ steps: [] }),
      "GET /stats": jsonResponse(EMPTY_STATS),
      "GET /conversations/r-ethan": () => conversation("r-ethan", "Software Architect", ethanActive, ethanMessages),
      "GET /conversations/r-maya": () => conversation("r-maya", "Design Advisor", mayaActive, []),
      "POST /expert/chat/stream": (url, options) => {
        const body = JSON.parse(options.body);
        if (body.conversation_id === "r-ethan") {
          ethanActive = "Design Advisor";
          ethanMessages.push(
            { type: "chat", sender: "user", message: body.message },
            { type: "system", message: "🎨 Maya Chen joined the conversation." },
            { type: "chat", sender: "expert", expert_key: "Design Advisor", expert: MAYA, message: "I'm Maya Chen. How can I help?" },
          );
          return sseResponse([
            sse("switch", { expert_key: "Design Advisor", expert: MAYA, notice: "🎨 Maya Chen joined the conversation." }),
            sse("done", { reply: "I'm Maya Chen. How can I help?", expert_key: "Design Advisor", saved: true }),
          ]);
        }
        mayaActive = "Software Architect";
        return sseResponse([
          sse("switch", { expert_key: "Software Architect", expert: ETHAN, notice: "👨‍💻 Ethan Walker joined the conversation." }),
          sse("done", { reply: "Ethan here, on the architecture.", expert_key: "Software Architect", saved: true }),
        ]);
      },
    });
    const user = userEvent.setup();
    renderAt("/expert/ethan");

    // TEST 1-2: Ethan's room; asking for Maya switches only the chatbot.
    const sidebar = () => screen.getByRole("button", { name: "Invite Another Expert →" }).parentElement;
    await user.type(await screen.findByLabelText(/Message Ethan/), "Can I speak with Maya Chen?");
    await user.click(screen.getByRole("button", { name: "Send →" }));
    expect(await screen.findByText("I'm Maya Chen. How can I help?")).toBeInTheDocument();
    expect(screen.getByText("🎨 Maya Chen joined the conversation.")).toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /expert/chat/stream").body.expert).toBe("Software Architect");

    expect(within(sidebar()).getByRole("heading", { name: "Ethan Walker" })).toBeInTheDocument();
    expect(within(sidebar()).getByText("Senior Software Architect")).toBeInTheDocument();
    expect(within(sidebar()).getByText("Microservices")).toBeInTheDocument();          // Ethan's expertise
    expect(within(sidebar()).queryByText("Maya Chen")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("heading", { name: "Maya Chen" })).toHaveLength(0);
    expect(screen.getByLabelText(/Message Ethan/)).toHaveAttribute("placeholder", "Ask Ethan about architecture...");
    expect(screen.getByRole("button", { name: "Explain your recommendation" })).toBeInTheDocument();  // Ethan's suggestions
    expect(screen.getByText(/continue working with Ethan Walker/)).toBeInTheDocument();

    // TEST 4-5: leave and come back to Ethan's page: still Ethan's room; the
    // chat continues with its saved role and history.
    await user.click(screen.getByRole("link", { name: "← All Experts" }));
    await user.click(await screen.findByRole("button", { name: "Consult Ethan Walker" }));
    expect(await screen.findByText("I'm Maya Chen. How can I help?")).toBeInTheDocument();
    expect(within(sidebar()).getByRole("heading", { name: "Ethan Walker" })).toBeInTheDocument();
    expect(screen.queryAllByRole("heading", { name: "Maya Chen" })).toHaveLength(0);

    // TEST 6-7: Maya's own room is Maya's; switching her chatbot to Ethan
    // leaves her page unchanged.
    await user.click(screen.getByRole("link", { name: "← All Experts" }));
    await user.click(await screen.findByRole("button", { name: "Consult Maya Chen" }));
    await user.type(await screen.findByLabelText(/Message Maya/), "Switch to Ethan");
    await user.click(screen.getByRole("button", { name: "Send →" }));
    expect(await screen.findByText("Ethan here, on the architecture.")).toBeInTheDocument();
    expect(within(sidebar()).getByRole("heading", { name: "Maya Chen" })).toBeInTheDocument();
    expect(within(sidebar()).getByText("Design Systems")).toBeInTheDocument();
    expect(screen.getByLabelText(/Message Maya/)).toHaveAttribute("placeholder", "Ask Maya about UI/UX...");

    // TEST 8: back to Ethan's page: Ethan's identity, unaffected by Maya's room.
    await user.click(screen.getByRole("link", { name: "← All Experts" }));
    await user.click(await screen.findByRole("button", { name: "Consult Ethan Walker" }));
    expect(await screen.findByText("I'm Maya Chen. How can I help?")).toBeInTheDocument();
    expect(within(sidebar()).getByRole("heading", { name: "Ethan Walker" })).toBeInTheDocument();
    expect(screen.queryByText("Ethan here, on the architecture.")).not.toBeInTheDocument();
  });

  it("restores the room and the chat role separately after a refresh", async () => {
    const report = { title: "Store plan", recommendation: "Modular monolith", description: "Because.", metrics: [] };
    const MAYA = { key: "Design Advisor", name: "Maya Chen", role: "Senior Product Designer", emoji: "🎨" };
    sessionStorage.setItem("expertos.active.room.ethan", "r9");
    mockFetch({
      "POST /expert/discovery": jsonResponse({ steps: [] }),
      "GET /stats": jsonResponse(EMPTY_STATS),
      "GET /conversations/r9": jsonResponse({
        id: "r9", kind: "expert_room", expert_key: "Software Architect", answers: { description: "Clothing store" },
        report, files: [], active_expert: "Design Advisor",
        messages: [
          { type: "chat", sender: "user", message: "can i speak with maya chen" },
          { type: "system", message: "🎨 Maya Chen joined the conversation." },
          { type: "chat", sender: "expert", expert_key: "Design Advisor", expert: MAYA, message: "I'm Maya Chen." },
        ],
      }),
      "POST /expert/chat/stream": sseResponse([sse("done", { reply: "Use bigger tap targets.", expert_key: "Design Advisor", saved: true })]),
    });
    const user = userEvent.setup();
    renderAt("/expert/ethan");
    expect(await screen.findByText("I'm Maya Chen.")).toBeInTheDocument();
    const sidebar = screen.getByRole("button", { name: "Invite Another Expert →" }).parentElement;
    expect(within(sidebar).getByRole("heading", { name: "Ethan Walker" })).toBeInTheDocument();

    // The restored chat role (Maya) is the one shown while answering.
    await user.type(screen.getByLabelText(/Message Ethan/), "How big should buttons be?");
    await user.click(screen.getByRole("button", { name: "Send →" }));
    expect(await screen.findByText("Use bigger tap targets.")).toBeInTheDocument();
  });

  it("lists previous conversations and reopens one with its report and chat", async () => {
    const report = { title: "Indexing plan", recommendation: "Add composite indexes", description: "Because.", metrics: [] };
    const { calls } = mockFetch({
      "POST /expert/discovery": jsonResponse({ steps: [] }),
      "GET /stats": jsonResponse(EMPTY_STATS),
      "GET /conversations": jsonResponse({ conversations: [
        { id: "r1", kind: "expert_room", title: "Stock system", updated_at: "2026-11-01T10:00:00Z", message_count: 2 },
      ] }),
      "GET /conversations/r1": jsonResponse({
        id: "r1", kind: "expert_room", answers: { description: "Stock system" }, report, files: [],
        messages: [{ type: "chat", sender: "user", message: "Which index?" },
                   { type: "chat", sender: "expert", message: "A composite one." }],
      }),
      "POST /expert/chat/stream": sseResponse([sse("token", { text: "Sure." }), sse("done", { reply: "Sure.", saved: true })]),
    });
    const user = userEvent.setup();
    renderAt("/expert/alex");

    const history = await screen.findByRole("list", { name: "Your conversations" });
    expect(new URL(calls.find((c) => c.key === "GET /conversations").url).searchParams.get("expert"))
      .toBe("Database Engineer");
    await user.click(within(history).getByText("Stock system"));

    expect(await screen.findByText("Add composite indexes")).toBeInTheDocument();
    expect(screen.getByText("A composite one.")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Message Alex/), "More?");
    await user.click(screen.getByRole("button", { name: "Send →" }));
    expect(await screen.findByText("Sure.")).toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /expert/chat/stream").body)
      .toEqual({ expert: "Database Engineer", conversation_id: "r1", message: "More?" });
    expect(screen.getByRole("button", { name: /Download report/ })).toBeInTheDocument();
  });
});

describe("Report export", () => {
  it("builds the Expert Room report from the real answers, report and discussion", () => {
    const { filename, text } = expertRoomReport({
      expert: { name: "Alex Morgan", role: "Senior Database Engineer", shortRole: "Database Engineer" },
      answers: { project_name: "Stock", description: "Inventory system" },
      report: { title: "Indexing plan", recommendation: "Add indexes", description: "Why.",
                metrics: [{ name: "p95 latency", value: "Under 200 ms" }] },
      messages: [{ sender: "user", text: "Which index?" }, { sender: "expert", text: "Composite." }],
      files: [{ filename: "schema.sql", note: null }],
    });
    expect(filename).toBe("stock-database-engineer.md");
    for (const expected of ["# Indexing plan", "**Description:** Inventory system", "- schema.sql",
                            "| p95 latency | Under 200 ms |", "**You:** Which index?", "**Alex Morgan:** Composite."]) {
      expect(text).toContain(expected);
    }
  });

  it("leaves out empty sections instead of inventing content", () => {
    const { text } = consultationReport({ project: "App", analysis: { architecture: "Monolith." }, messages: [], files: [] });
    expect(text).toContain("## Architecture Overview");
    expect(text).not.toContain("## Security Suggestions");
    expect(text).not.toContain("## Discussion");
  });
});
