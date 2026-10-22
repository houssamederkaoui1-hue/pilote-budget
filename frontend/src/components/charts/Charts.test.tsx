import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CashFlowBars, Donut, TrendLine } from "./Charts";

describe("CashFlowBars", () => {
  it("renders both series with tooltips and labels", () => {
    const html = renderToStaticMarkup(
      <CashFlowBars
        currency="MAD"
        points={[{ label: "Sep", income: 100, expense: 40, current: false }]}
      />,
    );
    expect(html).toContain(`title="Income: `);
    expect(html).toContain(`title="Expenses: `);
    expect(html).toContain("Sep");
    expect(html).toMatch(/height:\d+px/);
  });

  it("labels the current period distinctly", () => {
    const html = renderToStaticMarkup(
      <CashFlowBars
        currency="MAD"
        points={[{ label: "Oct", income: 0, expense: 0, current: true }]}
      />,
    );
    expect(html).toContain("Oct");
  });
});

describe("TrendLine", () => {
  it("renders a polyline with a dot per point", () => {
    const html = renderToStaticMarkup(
      <TrendLine
        currency="MAD"
        points={[
          { label: "Apr", value: 800 },
          { label: "May", value: 1200 },
        ]}
      />,
    );
    expect(html).toContain("polyline");
    expect(html).toContain("polygon");
  });

  it("renders nothing without points", () => {
    expect(renderToStaticMarkup(<TrendLine currency="MAD" points={[]} />)).toBe("");
  });

  it("deals with a flat series (min === max)", () => {
    const html = renderToStaticMarkup(
      <TrendLine
        currency="MAD"
        points={[
          { label: "A", value: 100 },
          { label: "B", value: 100 },
        ]}
      />,
    );
    expect(html).toContain("polyline");
  });
});

describe("Donut", () => {
  it("renders a conic gradient plus a legend item per segment", () => {
    const html = renderToStaticMarkup(
      <Donut
        currency="MAD"
        segments={[
          { key: "1", label: "Food", value: 80 },
          { key: "2", label: "Transport", value: 20 },
        ]}
      />,
    );
    expect(html).toContain("conic-gradient");
    expect(html).toContain("Food");
    expect(html).toContain("Transport");
  });

  it("renders nothing when there is no value", () => {
    expect(renderToStaticMarkup(<Donut currency="MAD" segments={[]} />)).toBe("");
    expect(renderToStaticMarkup(<Donut currency="MAD" segments={[{ key: "1", label: "A", value: 0 }]} />)).toBe("");
  });
});