import type { AnchorHTMLAttributes, HTMLAttributes } from "react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { Link } from "react-router-dom";

import "katex/dist/katex.min.css";

type Props = {
  text: string;
  className?: string;
};

/** Падение KaTeX / unified ломало весь пузырь — показываем сырой текст. */
class MarkdownErrorBoundary extends Component<
  { children: ReactNode; fallbackText: string },
  { err: Error | null }
> {
  state = { err: null as Error | null };

  static getDerivedStateFromError(err: Error): { err: Error } {
    return { err };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn("[ChatMarkdown]", error.message, info.componentStack?.split("\n").slice(0, 5).join(" "));
  }

  componentDidUpdate(prev: Readonly<{ children: ReactNode; fallbackText: string }>): void {
    if (prev.fallbackText !== this.props.fallbackText) {
      this.setState({ err: null });
    }
  }

  render(): ReactNode {
    if (this.state.err) {
      return (
        <div className="t-chat-md t-chat-md--fallback">
          <p className="t-chat-md--fallback-note">Не удалось отрисовать разметку; показывается сырой ответ:</p>
          <pre className="t-chat-plain">{this.props.fallbackText}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

/** Markdown в ответах ассистента: GFM + LaTeX ($…$, $$…$$, \\(…\\)); KaTeX без throw в рендере. */
export function ChatMarkdown({ text, className }: Props) {
  if (!text.trim()) return null;

  const components: Partial<Components> = {
    pre({ children }) {
      return <pre className="t-chat-pre">{children}</pre>;
    },
    code(props: HTMLAttributes<HTMLElement> & { inline?: boolean }) {
      const { className: cls, children, inline, ...rest } = props;
      if (inline) {
        return (
          <code className="t-chat-inline-code" {...rest}>
            {children}
          </code>
        );
      }
      return (
        <code className={cls} {...rest}>
          {children}
        </code>
      );
    },
    a(props: AnchorHTMLAttributes<HTMLAnchorElement>) {
      const { href, children, className, ...rest } = props;
      if (!href) return <span className={className}>{children}</span>;
      if (href.startsWith("/") && !href.startsWith("//")) {
        return (
          <Link to={href} className={className ?? "t-chat-md-link"}>
            {children}
          </Link>
        );
      }
      return (
        <a href={href} className={className} target="_blank" rel="noopener noreferrer" {...rest}>
          {children}
        </a>
      );
    },
  };

  return (
    <div className={className ?? "t-chat-md"}>
      <MarkdownErrorBoundary fallbackText={text}>
        <ReactMarkdown
          remarkPlugins={[
            remarkGfm,
            /* По умолчанию remark-math парсит $…$ как inline-math — нужно для ответов ассистента.
               Литеральный знак доллара в тексте: экранировать обратным слэшем ``\$`` или писать «5 USD». */
            remarkMath,
          ]}
          rehypePlugins={[
            [
              rehypeKatex,
              {
                throwOnError: false,
                strict: false,
                errorColor: "#fb7185",
              },
            ],
          ]}
          components={components}
        >
          {text}
        </ReactMarkdown>
      </MarkdownErrorBoundary>
    </div>
  );
}
