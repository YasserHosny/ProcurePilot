import { computeBaseQuantity } from "./normalisation";

describe("Pack normalisation arithmetic (Principle II, SC-007)", () => {
  it("computes exact integer pack quantities: 6 x 5 = 30", () => {
    expect(computeBaseQuantity(6, "5")).toBe("30");
    expect(computeBaseQuantity(6, "5.000000")).toBe("30");
  });

  it("computes exact decimal pack quantities: 3 x 0.33 = 0.99", () => {
    expect(computeBaseQuantity(3, "0.33")).toBe("0.99");
    expect(computeBaseQuantity(12, "0.750")).toBe("9");
    expect(computeBaseQuantity(10, "1.25")).toBe("12.5");
  });

  it("returns null for invalid, zero, or negative pack inputs", () => {
    expect(computeBaseQuantity(0, "5")).toBeNull();
    expect(computeBaseQuantity(-1, "5")).toBeNull();
    expect(computeBaseQuantity(6, "0")).toBeNull();
    expect(computeBaseQuantity(6, "-5")).toBeNull();
    expect(computeBaseQuantity(null, "5")).toBeNull();
    expect(computeBaseQuantity(6, null)).toBeNull();
    expect(computeBaseQuantity(6, "abc")).toBeNull();
  });
});
