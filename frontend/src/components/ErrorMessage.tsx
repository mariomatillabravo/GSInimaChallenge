import { ApiError } from "../api/client";
import { describeError } from "../lib/errors";
import styles from "./ErrorMessage.module.css";

/** A failed request, with the request ID that identifies it in the API logs when there is one. */
export function ErrorMessage({ error }: { error: unknown }) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div role="alert" className={styles.error}>
      <p className={styles.message}>{describeError(error)}</p>
      {requestId === null ? null : (
        <p className={styles.requestId}>
          Request ID: <code>{requestId}</code>
        </p>
      )}
    </div>
  );
}
