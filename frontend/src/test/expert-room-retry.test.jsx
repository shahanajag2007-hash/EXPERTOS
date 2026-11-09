import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ExpertRoom from "../pages/ExpertRoom";
import { listConsultations } from "../services/consultations";
import { __resetStatsCache } from "../hooks/useStats";
import { EMPTY_STATS, jsonResponse, mockFetch } from "./helpers";

const STEPS = [
  { title: "Project", fields: [{ name: "project_name", label: "Project Name" }, { name: "description", label: "Tell Alex About Your Project" }] },
  { title: "Context", fields: [{ name: "database", label: "Current Database" }] },
  { title: "Goals", fields: [{ name: "constraints", label: "Constraints" }] },
];

const REPORT = {
  title: "Booking Integrity", recommendation: "Use row-level locks", description: "Details.",
  metrics: [{ name: "Double bookings per week", value: "Zero" }],
  consultation: { id: "c-9", token: "tok-9" },
};

const QUOTA_ERROR = {
  error: "All of ExpertOS's AI providers have reached their usage limits. Please try again later.",
  code: "account_rate_limit", retryable: true, retry_at: "2026-10-20T00:00:00+00:00",
  providers: [{ provider: "OpenRouter", category: "account_rate_limit", skipped: false }],
};

function renderRoom() {
  return render(
    <MemoryRouter initialEntries={["/expert/alex"]}>
      <Routes><Route path="/expert/:id" element={<ExpertRoom />} /></Routes>
    </MemoryRouter>,
  );
}

async function completeWizard() {
  await userEvent.type(await screen.findByLabelText("Tell Alex About Your Project"), "A yoga booking app with double bookings");
  await userEvent.click(screen.getByRole("button", { name: /Continue Discovery/ }));
  await userEvent.click(screen.getByRole("button", { name: /Continue Discovery/ }));
  await userEvent.click(screen.getByRole("button", { name: /Let Alex Review/ }));
}

describe("Expert Room retry", () => {
  beforeEach(() => __resetStatsCache());

  it("shows the real error, then retries once per click and records one consultation", async () => {
    let attempt = 0;
    const releases = [];
    const { calls } = mockFetch({
      "GET /stats": jsonResponse(EMPTY_STATS),
      "POST /expert/discovery": jsonResponse({ steps: STEPS }),
      "POST /expert/recommend": () => {
        attempt += 1;
        if (attempt === 1) return jsonResponse(QUOTA_ERROR, 503);
        // Hold the retry open so a double click lands while it's in flight.
        return new Promise((resolve) => releases.push(() => resolve(jsonResponse(REPORT))));
      },
    });
    renderRoom();
    await completeWizard();

    // Failure: the backend's message and the reported reset time are shown.
    expect(await screen.findByText("Alex couldn't finish the review")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("All of ExpertOS's AI providers have reached their usage limits");
    expect(screen.getByText(/Expected to be available again around/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "← Edit Answers" })).toBeInTheDocument();

    // Double click on Try Again: a loading state appears and only one request is sent.
    await userEvent.dblClick(screen.getByRole("button", { name: "Try Again" }));
    expect(screen.getByRole("status", { name: "Loading recommendation" })).toBeInTheDocument();
    expect(calls.filter((c) => c.key === "POST /expert/recommend")).toHaveLength(2);

    releases.forEach((release) => release());
    expect(await screen.findByText("Use row-level locks")).toBeInTheDocument();
    expect(calls.filter((c) => c.key === "POST /expert/recommend")).toHaveLength(2);
    expect(listConsultations().map((c) => c.id)).toEqual(["c-9"]);

    // The retry resent the same answers.
    const bodies = calls.filter((c) => c.key === "POST /expert/recommend").map((c) => c.body);
    expect(bodies[1]).toEqual(bodies[0]);
  });

  it("makes repeated failures visible and lets the user edit their answers", async () => {
    mockFetch({
      "GET /stats": jsonResponse(EMPTY_STATS),
      "POST /expert/discovery": jsonResponse({ steps: STEPS }),
      "POST /expert/recommend": jsonResponse({ ...QUOTA_ERROR, retry_at: null }, 503),
    });
    renderRoom();
    await completeWizard();

    await screen.findByText("Alex couldn't finish the review");
    expect(screen.queryByText(/Expected to be available again/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try Again" }));
    expect(await screen.findByText(/Still unavailable after 2 attempts/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "← Edit Answers" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Tell Alex About Your Project")).toHaveValue("A yoga booking app with double bookings"),
    );
    expect(listConsultations()).toHaveLength(0);
  });
});
