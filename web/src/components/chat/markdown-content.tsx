"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const mdComponents: React.ComponentProps<typeof ReactMarkdown>["components"] = {
  p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
  hr: () => <hr className="mb-2" />,
  h3: ({ children }) => <h3 className="mb-3">{children}</h3>,
  code: ({ children, className }) => {
    const isBlock = className?.includes("language-");
    return isBlock ? (
      <code className="block bg-muted/40 border border-border/30 rounded px-3 py-2 text-[11px] font-mono overflow-x-auto my-2">
        {children}
      </code>
    ) : (
      <code className="bg-muted/40 rounded px-1 py-0.5 text-[11px] font-mono">{children}</code>
    );
  },
  table: ({ children }) => (
    <div className="overflow-x-auto my-2">
      <table className="text-[11px] font-mono border-collapse w-full">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border/30 px-2 py-1 text-left text-muted-foreground font-medium bg-muted/20">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="border border-border/30 px-2 py-1">{children}</td>,
  ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-0.5">{children}</ol>,
  li: ({ children }) => <li className="text-sm">{children}</li>,
  strong: ({ children }) => <strong className="text-foreground font-semibold">{children}</strong>,
};

export function MarkdownContent({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
      {text}
    </ReactMarkdown>
  );
}
