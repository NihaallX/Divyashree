import type { ReactNode } from "react"

type ContentShellProps = {
  eyebrow?: string
  title: string
  description?: string
  children: ReactNode
  maxWidthClassName?: string
}

export function ContentShell({
  eyebrow,
  title,
  description,
  children,
  maxWidthClassName = "max-w-5xl",
}: ContentShellProps) {
  return (
    <main className="relative min-h-screen overflow-x-hidden noise-overlay bg-background text-foreground px-6 py-12 lg:px-12">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-16 top-0 h-72 w-72 rounded-full bg-foreground/5 blur-3xl" />
        <div className="absolute right-0 top-28 h-64 w-64 rounded-full bg-foreground/5 blur-3xl" />
      </div>

      <div className={`relative z-10 mx-auto ${maxWidthClassName} space-y-8`}>
        <header className="border-b border-foreground/10 pb-6">
          {eyebrow ? (
            <span className="inline-flex items-center gap-3 text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
              <span className="h-px w-7 bg-foreground/30" />
              {eyebrow}
            </span>
          ) : null}
          <h1 className="mt-3 text-4xl font-display tracking-tight lg:text-5xl">{title}</h1>
          {description ? <p className="mt-3 max-w-3xl text-muted-foreground">{description}</p> : null}
        </header>

        {children}
      </div>
    </main>
  )
}
