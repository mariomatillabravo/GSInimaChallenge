import { describe, expect, it } from "vitest";

import { dailyMeasurements, emptyMeasurements } from "../test/fixtures";
import { emptyRowsText, hasData } from "./result";

describe("hasData", () => {
  it("is false when every bucket is empty", () => {
    expect(hasData(emptyMeasurements)).toBe(false);
  });

  it("is true when at least one bucket has observations", () => {
    const oneFull = {
      ...emptyMeasurements,
      data: emptyMeasurements.data.map((row, index) =>
        index === 0 ? { ...row, samples: 1 } : row,
      ),
    };

    expect(hasData(oneFull)).toBe(true);
    expect(hasData(dailyMeasurements)).toBe(true);
  });

  it("counts ten-minute records, which have no samples field, as data", () => {
    const records = {
      ...dailyMeasurements,
      data: [{ station: "Juan Carlos I", datetime: "2025-03-30T00:00:00+01:00", speed_ms: 2.0 }],
    };

    expect(hasData(records)).toBe(true);
    expect(hasData({ ...dailyMeasurements, data: [] })).toBe(false);
  });
});

describe("emptyRowsText", () => {
  it("names the buckets of the aggregation level, in singular or plural", () => {
    expect(emptyRowsText("hourly", 169)).toBe("169 empty hours");
    expect(emptyRowsText("daily", 1)).toBe("1 empty day");
    expect(emptyRowsText("monthly", 2)).toBe("2 empty months");
    expect(emptyRowsText("none", 3)).toBe("3 empty rows");
  });
});
