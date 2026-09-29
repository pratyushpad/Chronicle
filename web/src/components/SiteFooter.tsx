import Link from "next/link";

const ISSUES = "https://github.com/pratyushpad/Chronicle/issues";

/** Site footer: where roles come from, and how a company asks to be removed. */
export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-border-light">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-6 py-8 font-sans text-xs text-muted-foreground md:flex-row md:items-center md:justify-between md:px-8 lg:px-12">
        <p>
          Roles come from each company&rsquo;s own public careers board.{" "}
          <Link href="/companies" className="underline underline-offset-4 hover:text-foreground">
            See every company
          </Link>{" "}
          or the{" "}
          <Link href="/status" className="underline underline-offset-4 hover:text-foreground">
            data status
          </Link>
          .
        </p>
        <p>
          A company that wants its board removed can{" "}
          <a href={ISSUES} className="underline underline-offset-4 hover:text-foreground" rel="noopener noreferrer">
            open an issue on GitHub
          </a>
          .
        </p>
      </div>
    </footer>
  );
}
