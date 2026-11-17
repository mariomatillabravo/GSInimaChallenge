import { useState } from "react";

import type { MeasurementsResponse } from "../api/client";
import { emptyRowsText } from "../lib/result";
import styles from "./EmptyResult.module.css";
import { MeasurementsTable } from "./MeasurementsTable";

interface Props {
  result: MeasurementsResponse;
  csvUrl: string | null;
}

/**
 * A result without any data: the summary above already carries the API's notice, so the empty
 * charts are left out and the empty rows stay one click away, for whoever wants to see them.
 */
export function EmptyResult({ result, csvUrl }: Props) {
  const [revealed, setRevealed] = useState(false);
  if (result.data.length === 0) {
    return null;
  }
  if (revealed) {
    return <MeasurementsTable result={result} csvUrl={csvUrl} />;
  }
  return (
    <button
      type="button"
      className={styles.reveal}
      onClick={() => {
        setRevealed(true);
      }}
    >
      Show the {emptyRowsText(result.metadata.aggregation, result.data.length)}
    </button>
  );
}
