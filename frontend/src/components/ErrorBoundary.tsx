import { Component, type ReactNode } from "react";

interface Props {
  /** Shown instead of the children once they have failed. */
  fallback: ReactNode;
  children: ReactNode;
}

interface State {
  failed: boolean;
}

/**
 * Contains a failure of its children, such as code that could not be loaded, so the rest of the
 * page keeps working. React only offers this as a class component.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
