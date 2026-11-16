import { type SubmitEvent, useId, useState } from "react";

import type { ApiError, MeasurementTypeId, MetaResponse, Station } from "../api/client";
import type { SubmittedQuery } from "../api/queries";
import { AGGREGATION_LABELS } from "../lib/labels";
import {
  type FieldErrors,
  type FormField,
  type FormValues,
  formFieldOf,
  initialValues,
  toQuery,
  validate,
} from "../lib/queryForm";
import styles from "./QueryForm.module.css";

interface Props {
  meta: MetaResponse;
  stations: Station[];
  /** A request is in flight. */
  pending: boolean;
  /** An API error about one of the form's fields, shown next to it. */
  fieldError: ApiError | null;
  onSubmit: (query: SubmittedQuery) => void;
}

export function QueryForm({ meta, stations, pending, fieldError, onSubmit }: Props) {
  const [values, setValues] = useState<FormValues>(() => initialValues(meta, stations, new Date()));
  const [errors, setErrors] = useState<FieldErrors>({});
  const id = useId();

  // Problems found by the form come first; the API's verdict is shown when the form found none.
  const hasFormErrors = Object.keys(errors).length > 0;
  const apiField = fieldError === null || hasFormErrors ? null : formFieldOf(fieldError.parameter);

  function message(field: FormField) {
    const text = errors[field] ?? (apiField === field ? fieldError?.message : undefined);
    if (text === undefined) {
      return { invalid: false, describedBy: undefined, element: null };
    }
    const requestId = apiField === field ? fieldError?.requestId : null;
    return {
      invalid: true,
      describedBy: `${id}-${field}-error`,
      element: (
        // One text node up to the ID: screen readers build the description from the text of
        // each element, trimmed, so a space at the start of a separate element would be lost.
        <p id={`${id}-${field}-error`} className={styles.error}>
          {requestId ? `${text} Request ID: ` : text}
          {requestId ? <code className={styles.requestId}>{requestId}</code> : null}
        </p>
      ),
    };
  }

  function update(changes: Partial<FormValues>) {
    setValues((current) => ({ ...current, ...changes }));
  }

  function toggleType(type: MeasurementTypeId, checked: boolean) {
    // Rebuilt in the API's order, so the columns never depend on the order of the clicks.
    const types = meta.measurement_types
      .map((candidate) => candidate.id)
      .filter((candidate) => (candidate === type ? checked : values.types.includes(candidate)));
    update({ types });
  }

  function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const problems = validate(values, meta);
    setErrors(problems);
    if (Object.keys(problems).length === 0) {
      onSubmit(toQuery(values));
    }
  }

  const station = message("station");
  const start = message("start");
  const end = message("end");
  const aggregation = message("aggregation");
  const types = message("types");
  const maxRangeDays = meta.aggregations.find(
    (level) => level.id === values.aggregation,
  )?.max_range_days;

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate aria-label="Query">
      <div className={styles.fields}>
        <div className={styles.field}>
          <label htmlFor={`${id}-station`}>Station</label>
          <select
            id={`${id}-station`}
            value={values.stationId}
            aria-invalid={station.invalid}
            aria-describedby={station.describedBy}
            onChange={(event) => {
              update({ stationId: event.target.value });
            }}
          >
            {stations.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
          {station.element}
        </div>

        <div className={styles.field}>
          <label htmlFor={`${id}-start`}>Start</label>
          <input
            id={`${id}-start`}
            type="datetime-local"
            value={values.start}
            aria-invalid={start.invalid}
            aria-describedby={start.describedBy}
            onChange={(event) => {
              update({ start: event.target.value });
            }}
          />
          {start.element}
        </div>

        <div className={styles.field}>
          <label htmlFor={`${id}-end`}>End (included)</label>
          <input
            id={`${id}-end`}
            type="datetime-local"
            value={values.end}
            aria-invalid={end.invalid}
            aria-describedby={end.describedBy}
            onChange={(event) => {
              update({ end: event.target.value });
            }}
          />
          {end.element}
        </div>

        <div className={styles.field}>
          <label htmlFor={`${id}-aggregation`}>Aggregation</label>
          <select
            id={`${id}-aggregation`}
            value={values.aggregation}
            aria-invalid={aggregation.invalid}
            aria-describedby={[`${id}-aggregation-limit`, aggregation.describedBy].join(" ").trim()}
            onChange={(event) => {
              const level = meta.aggregations.find((option) => option.id === event.target.value);
              if (level) {
                update({ aggregation: level.id });
              }
            }}
          >
            {meta.aggregations.map((level) => (
              <option key={level.id} value={level.id}>
                {AGGREGATION_LABELS[level.id]}
              </option>
            ))}
          </select>
          <p id={`${id}-aggregation-limit`} className={styles.fieldHint}>
            {maxRangeDays === null || maxRangeDays === undefined
              ? "Any range length."
              : `Ranges up to ${String(maxRangeDays)} days.`}
          </p>
          {aggregation.element}
        </div>

        <fieldset
          className={styles.types}
          aria-invalid={types.invalid}
          aria-describedby={types.describedBy}
        >
          <legend>Measurements</legend>
          {meta.measurement_types.map((type) => (
            <label key={type.id} className={styles.checkbox}>
              <input
                type="checkbox"
                checked={values.types.includes(type.id)}
                onChange={(event) => {
                  toggleType(type.id, event.target.checked);
                }}
              />
              {type.label}
            </label>
          ))}
          {types.element}
        </fieldset>
      </div>

      <div className={styles.actions}>
        <button type="submit" className={styles.submit} disabled={pending}>
          {pending ? "Loading…" : "Show data"}
        </button>
        <p className={styles.hint}>Dates and times in {meta.default_input_timezone} time.</p>
      </div>
    </form>
  );
}
