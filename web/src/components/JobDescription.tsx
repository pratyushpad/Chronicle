import { Fragment } from "react";
import type { DescriptionBlock, Inline, ListBlock } from "@/lib/description";
import { isSafeHref } from "@/lib/description";

/** Renders typed description blocks as elements. There is deliberately no HTML path. */
export function JobDescription({ blocks }: { blocks: DescriptionBlock[] }) {
  return (
    <div className="job-description break-words font-body text-base leading-[1.75] text-foreground">
      {blocks.map((block, i) => (
        <Block key={i} block={block} />
      ))}
    </div>
  );
}

function Block({ block }: { block: DescriptionBlock }) {
  switch (block.type) {
    case "heading": {
      const content = <Inlines nodes={block.content} />;
      // One step below the page's h1/h2 structure: posting sections read as h3/h4.
      if (block.level === 4) {
        return <h4 className="mt-6 mb-2 font-sans text-base font-semibold text-foreground">{content}</h4>;
      }
      return <h3 className="mt-8 mb-3 font-display text-xl leading-snug text-foreground">{content}</h3>;
    }
    case "list":
      return <List block={block} />;
    case "paragraph":
      return (
        <p className="my-4">
          <Inlines nodes={block.content} />
        </p>
      );
    default:
      return null;
  }
}

function List({ block, nested = false }: { block: ListBlock; nested?: boolean }) {
  const Tag = block.ordered ? "ol" : "ul";
  return (
    <Tag
      className={
        (block.ordered ? "list-decimal" : "list-disc") +
        (nested ? " mt-1 mb-0 pl-6" : " my-4 pl-6") +
        " marker:text-muted-foreground"
      }
    >
      {block.items.map((item, i) => (
        <li key={i} className="pl-1 [&+li]:mt-1.5">
          <Inlines nodes={item.content} />
          {item.children.map((child, j) => (
            <List key={j} block={child} nested />
          ))}
        </li>
      ))}
    </Tag>
  );
}

function Inlines({ nodes }: { nodes: Inline[] }) {
  return (
    <>
      {nodes.map((node, i) => {
        switch (node.type) {
          case "text":
            return <Fragment key={i}>{node.text}</Fragment>;
          case "break":
            return <br key={i} />;
          case "strong":
            return (
              <strong key={i} className="font-semibold">
                <Inlines nodes={node.content} />
              </strong>
            );
          case "em":
            return (
              <em key={i}>
                <Inlines nodes={node.content} />
              </em>
            );
          case "link":
            if (!isSafeHref(node.href)) return <Inlines key={i} nodes={node.content} />;
            return (
              <a
                key={i}
                href={node.href}
                target="_blank"
                rel="noopener noreferrer nofollow ugc"
                className="underline underline-offset-4 hover:text-muted-foreground"
              >
                <Inlines nodes={node.content} />
              </a>
            );
          default:
            return null;
        }
      })}
    </>
  );
}
