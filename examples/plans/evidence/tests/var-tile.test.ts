// Sample test source for the worked example (not executed here). AC tags link tests to
// acceptance criteria for ac_coverage.py.
import { render, screen } from "@testing-library/react";
import { VarTile } from "../VarTile";

describe("VarTile", () => {
  it("shows VaR and as-of time [ST-1/AC-1]", async () => {
    render(<VarTile book="EQ-LON-01" />);
    expect(await screen.findByText("1,250,000 USD")).toBeTruthy();
  });

  // @ac ST-1/AC-2
  it("marks VaR older than 15 minutes as stale", async () => {
    render(<VarTile book="EQ-LON-01" now="2026-10-20T11:00:00Z" />);
    expect(await screen.findByText(/stale/)).toBeTruthy();
  });

  it("shows VaR unavailable on API error [ST-1/AC-3]", async () => {
    render(<VarTile book="BROKEN" />);
    expect(await screen.findByText("VaR unavailable")).toBeTruthy();
  });

  it("renders the book name", () => {
    render(<VarTile book="EQ-LON-01" />);
  });
});
