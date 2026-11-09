import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { __resetStatsCache } from "../hooks/useStats";
import { EMPTY_STATS, jsonResponse, mockFetch } from "./helpers";

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("Routing and navigation", () => {
  beforeEach(() => {
    __resetStatsCache();
    mockFetch({ "GET /stats": jsonResponse(EMPTY_STATS) });
  });

  it.each([
    ["About", "About ExpertOS"],
    ["Privacy", "Privacy Policy"],
    ["Terms", "Terms of Use"],
    ["Contact", "Contact Us"],
  ])("footer link %s opens its page", async (link, heading) => {
    renderAt("/");
    const footer = screen.getByRole("contentinfo");
    await userEvent.click(within(footer).getByRole("link", { name: link }));
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  });

  it.each(["/about", "/privacy", "/terms", "/contact"])("%s loads directly (refresh-safe)", (path) => {
    renderAt(path);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });

  it("still shows the 404 page for unknown routes", () => {
    renderAt("/no/such/page");
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it("sign in page offers an optional account", () => {
    renderAt("/signin");
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByText(/An account is optional/)).toBeInTheDocument();
    expect(document.querySelector('input[type="password"]')).not.toBeNull();
    expect(screen.getByRole("button", { name: "Create an account" })).toBeInTheDocument();
  });

  it("mobile menu opens and navigates", async () => {
    renderAt("/");
    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const menu = document.getElementById("mobile-menu");
    await userEvent.click(within(menu).getByRole("link", { name: "Expert Panel" }));
    expect(await screen.findByRole("heading", { name: /Multiple Experts/ })).toBeInTheDocument();
    expect(document.getElementById("mobile-menu")).toBeNull();
  });

  it("expert cards show real stats instead of fabricated ratings", async () => {
    renderAt("/experts");
    expect((await screen.findAllByText("No ratings yet")).length).toBe(6);
    expect(screen.getAllByText("No consultations yet").length).toBe(6);
    expect(screen.queryByText(/2,847/)).not.toBeInTheDocument();
  });
});

describe("Contact form", () => {
  beforeEach(() => __resetStatsCache());

  it("validates fields before sending", async () => {
    const { fetchMock } = mockFetch({});
    renderAt("/contact");
    await userEvent.click(screen.getByRole("button", { name: "Send Message" }));
    expect(screen.getByText("Please enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Please enter a subject.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("only shows success after the server confirms", async () => {
    const { calls } = mockFetch({ "POST /contact": jsonResponse({ status: "received" }, 201) });
    renderAt("/contact");
    await userEvent.type(screen.getByLabelText(/^Email/), "ana@example.com");
    await userEvent.type(screen.getByLabelText(/^Subject/), "Question");
    await userEvent.type(screen.getByLabelText(/^Message/), "How do ratings work?");
    await userEvent.click(screen.getByRole("button", { name: "Send Message" }));

    expect(await screen.findByText("Your message was received.")).toBeInTheDocument();
    expect(calls[0].body).toMatchObject({ email: "ana@example.com", subject: "Question", website: "" });
  });

  it("shows the server error instead of success when sending fails", async () => {
    mockFetch({ "POST /contact": jsonResponse({ error: "Too many submissions. Please try again later." }, 429) });
    renderAt("/contact");
    await userEvent.type(screen.getByLabelText(/^Email/), "ana@example.com");
    await userEvent.type(screen.getByLabelText(/^Subject/), "Question");
    await userEvent.type(screen.getByLabelText(/^Message/), "How do ratings work?");
    await userEvent.click(screen.getByRole("button", { name: "Send Message" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many submissions");
    expect(screen.queryByText("Your message was received.")).not.toBeInTheDocument();
  });
});
