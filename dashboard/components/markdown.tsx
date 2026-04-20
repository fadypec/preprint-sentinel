import ReactMarkdown from "react-markdown";

type Props = {
  children: string;
};

/**
 * Renders markdown text with basic styling for paragraphs, bold, lists.
 * Used for LLM-generated assessment summaries and reasoning.
 */
export function Markdown({ children }: Props) {
  return (
    <ReactMarkdown
      disallowedElements={['script', 'iframe', 'object', 'embed', 'form']}
      components={{
        p: (props) => <p className="mb-2 last:mb-0">{props.children}</p>,
        strong: (props) => <strong className="font-semibold">{props.children}</strong>,
        ol: (props) => <ol className="mb-2 ml-4 list-decimal space-y-1 last:mb-0">{props.children}</ol>,
        ul: (props) => <ul className="mb-2 ml-4 list-disc space-y-1 last:mb-0">{props.children}</ul>,
        li: (props) => <li>{props.children}</li>,
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
