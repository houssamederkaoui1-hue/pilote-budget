import { describe, expect, it } from "vitest";

import { changeHint, severityLabel, sortInsights, sourceLabel, sourceTone } from "./assistant";
import type { AssistantInsight } from "../types/api";

function insight(id: string, severity: AssistantInsight["severity"], priority: number): AssistantInsight {
  return {
    id,
    severity,
    category: "spending",
    title: id,
    explanation: "x",
    metric: null,
    actionable: false,
    priority,
    generated_at: null,
  };
}

describe("sortInsights", () => {
  it("orders by severity: critical → warning → success → info", () => {
    const sorted = sortInsights([
      insight("info", "info", 1),
      insight("critical", "critical", 1),
      insight("warning", "warning", 1),
      insight("success", "success", 1),
    ]);
    expect(sorted.map((item) => item.severity)).toEqual(["critical", "warning", "success", "info"]);
  });

  it("breaks ties by priority descending", () => {
    const sorted = sortInsights([
      insight("low", "warning", 1),
      insight("high", "warning", 9),
    ]);
    expect(sorted[0].id).toBe("high");
  });

  it("does not mutate the input", () => {
    const input = [insight("a", "success", 1), insight("b", "critical", 2)];
    sortInsights(input);
    expect(input[0].severity).toBe("success");
  });
});

describe("severityLabel", () => {
  it("capitalizes the severity token", () => {
    expect(severityLabel("critical")).toBe("Critical");
    expect(severityLabel("info")).toBe("Info");
  });
});

describe("sourceLabel", () => {
  it("describes where numbers came from", () => {
    expect(sourceLabel("ledger")).toBe("From your ledger");
    expect(sourceLabel("plan")).toBe("From your plan");
    expect(sourceLabel("estimate")).toBe("Estimate");
    expect(sourceLabel("assistant")).toBe("Assistant");
  });
});

describe("sourceTone", () => {
  it("maps sources to badge tones", () => {
    expect(sourceTone("ledger")).toBe("positive");
    expect(sourceTone("plan")).toBe("accent");
    expect(sourceTone("estimate")).toBe("warning");
    expect(sourceTone("assistant")).toBe("neutral");
  });
});

describe("changeHint", () => {
  it("handles null", () => {
    expect(changeHint(null)).toBe("");
  });

  it("reports direction and magnitude", () => {
    expect(changeHint(12.34)).toBe("up 12.3%");
    expect(changeHint(-3)).toBe("down 3.0%");
  });

  it("reports a flat change", () => {
    expect(changeHint(0)).toBe("unchanged");
  });
});