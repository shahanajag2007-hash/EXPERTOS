import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import RatingSection from "../components/Rating/RatingSection";
import { listConsultations, rememberConsultation } from "../services/consultations";
import { __resetStatsCache } from "../hooks/useStats";
import { EMPTY_STATS, jsonResponse, mockFetch } from "./helpers";

const CONSULTATION = { id: "c-1", token: "secret-token" };

function renderSection() {
  return render(
    <MemoryRouter>
      <RatingSection />
    </MemoryRouter>,
  );
}

describe("Rating section", () => {
  beforeEach(() => __resetStatsCache());

  it("explains that a completed consultation is needed first", () => {
    renderSection();
    expect(screen.getByText("How was your ExpertOS experience?")).toBeInTheDocument();
    expect(screen.getByText(/tied to a completed consultation/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start a consultation/i })).toHaveAttribute("href", "/experts");
  });

  it("requires a star rating before submitting", async () => {
    rememberConsultation(CONSULTATION, { label: "Database Engineer recommendation" });
    const { fetchMock } = mockFetch({});
    renderSection();

    await userEvent.click(screen.getByRole("button", { name: "Submit Rating" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Please choose a rating");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits a keyboard-selected rating with feedback and the consultation token", async () => {
    rememberConsultation(CONSULTATION, { label: "Database Engineer recommendation" });
    const { calls } = mockFetch({
      "POST /consultations/c-1/rating": jsonResponse({ status: "saved" }, 201),
      "GET /stats": jsonResponse(EMPTY_STATS),
    });
    renderSection();

    // Keyboard: focus the first star and move with the arrow keys.
    const first = screen.getByLabelText(/^1 star/);
    first.focus();
    await userEvent.keyboard("[Space]");
    await userEvent.keyboard("[ArrowRight][ArrowRight][ArrowRight]");
    expect(screen.getByLabelText(/^4 stars/)).toBeChecked();
    expect(screen.getByText("4 of 5: Very good")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/feedback/i), "Clear and useful");
    await userEvent.click(screen.getByRole("button", { name: "Submit Rating" }));

    expect(await screen.findByText("Thank you for helping us improve ExpertOS!")).toBeInTheDocument();
    const post = calls.find((c) => c.key === "POST /consultations/c-1/rating");
    expect(post.body).toEqual({ stars: 4, feedback: "Clear and useful" });
    expect(post.options.headers["X-Consultation-Token"]).toBe("secret-token");
    expect(listConsultations()[0].rated).toBe(true);
  });

  it("does not send duplicate submissions on a double click", async () => {
    rememberConsultation(CONSULTATION);
    let resolve;
    const { calls } = mockFetch({
      "POST /consultations/c-1/rating": () => new Promise((r) => { resolve = r; }),
      "GET /stats": jsonResponse(EMPTY_STATS),
    });
    renderSection();

    await userEvent.click(screen.getByLabelText(/^5 stars/));
    const button = screen.getByRole("button", { name: "Submit Rating" });
    await userEvent.dblClick(button);
    expect(calls.filter((c) => c.key.startsWith("POST")).length).toBe(1);
    expect(screen.getByRole("button", { name: "Submitting..." })).toBeDisabled();

    resolve(jsonResponse({ status: "saved" }, 201));
    expect(await screen.findByText(/Thank you/)).toBeInTheDocument();
  });

  it("treats an already-rated consultation as done instead of counting it again", async () => {
    rememberConsultation(CONSULTATION);
    mockFetch({
      "POST /consultations/c-1/rating": jsonResponse({ error: "This consultation has already been rated. Thank you!" }, 409),
    });
    renderSection();

    await userEvent.click(screen.getByLabelText(/^3 stars/));
    await userEvent.click(screen.getByRole("button", { name: "Submit Rating" }));
    expect(await screen.findByText(/Thank you for helping/)).toBeInTheDocument();
    expect(listConsultations()[0].rated).toBe(true);
  });

  it("shows server errors and lets the user try again", async () => {
    rememberConsultation(CONSULTATION);
    mockFetch({ "POST /consultations/c-1/rating": jsonResponse({ error: "Too many submissions." }, 429) });
    renderSection();

    await userEvent.click(screen.getByLabelText(/^5 stars/));
    await userEvent.click(screen.getByRole("button", { name: "Submit Rating" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many submissions.");
    expect(screen.getByRole("button", { name: "Submit Rating" })).toBeEnabled();
  });
});
