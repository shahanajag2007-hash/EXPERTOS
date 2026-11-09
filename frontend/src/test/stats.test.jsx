import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import Statistics from "../components/Statistics/Statistics";
import { __resetStatsCache } from "../hooks/useStats";
import { EMPTY_STATS, jsonResponse, mockFetch } from "./helpers";

describe("Homepage statistics", () => {
  beforeEach(() => __resetStatsCache());

  it("shows real initial values and empty states on a new installation", async () => {
    mockFetch({ "GET /stats": jsonResponse(EMPTY_STATS) });
    render(<Statistics />);

    const consultations = await screen.findByTestId("stat-consultations");
    expect(within(consultations).getByText("0")).toBeInTheDocument();
    expect(within(screen.getByTestId("stat-experts")).getByText("6")).toBeInTheDocument();
    expect(screen.getByText("Awaiting first ratings")).toBeInTheDocument();
    expect(screen.getByText("Measuring response times")).toBeInTheDocument();

    // None of the old hardcoded figures.
    expect(screen.queryByText("14,500+")).not.toBeInTheDocument();
    expect(screen.queryByText("98%")).not.toBeInTheDocument();
    expect(screen.queryByText("<30s")).not.toBeInTheDocument();
  });

  it("shows measured values from the backend", async () => {
    mockFetch({
      "GET /stats": jsonResponse({
        ...EMPTY_STATS,
        completed_consultations: 1234,
        ratings: { total: 3, positive: 2, satisfaction_rate: 66.7, average_stars: 3.67, positive_threshold: 4 },
        response_time: { ...EMPTY_STATS.response_time, average_seconds: 12.43, samples: 40, status: "measured" },
      }),
    });
    render(<Statistics />);

    expect(await screen.findByText("1,234")).toBeInTheDocument();
    expect(screen.getByText("67%")).toBeInTheDocument();
    expect(screen.getByText(/from 3 ratings/)).toBeInTheDocument();
    expect(screen.getByText("12.4s")).toBeInTheDocument();
    expect(screen.getByText("Average Response")).toBeInTheDocument();
  });

  it("says statistics are unavailable when the backend is down", async () => {
    mockFetch({ "GET /stats": () => Promise.reject(new TypeError("Failed to fetch")) });
    render(<Statistics />);
    expect(await screen.findByText(/statistics are unavailable/i)).toBeInTheDocument();
  });
});
