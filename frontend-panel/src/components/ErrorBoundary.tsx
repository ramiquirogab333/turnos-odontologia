import { Component, type ReactNode } from 'react';

interface Props {
  readonly children: ReactNode;
  readonly onReintentar: () => void;
  readonly fallback: (reintentar: () => void, error: Error) => ReactNode;
}

interface Estado {
  readonly error: Error | null;
}

/** Captura el rechazo de una promesa leída con `use()` y ofrece reintentar. */
export class ErrorBoundary extends Component<Props, Estado> {
  override state: Estado = { error: null };

  static getDerivedStateFromError(error: Error): Estado {
    return { error };
  }

  private readonly reintentar = (): void => {
    this.props.onReintentar();
    this.setState({ error: null });
  };

  override render(): ReactNode {
    if (this.state.error) return this.props.fallback(this.reintentar, this.state.error);
    return this.props.children;
  }
}
