import { ApiError } from "../api/client";

/** A message for the user. The API's own messages already say what to change or when to retry. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  // fetch rejects with a TypeError when no answer arrives at all.
  if (error instanceof TypeError) {
    return "Cannot reach the API. Check your connection and that the API is running.";
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}
