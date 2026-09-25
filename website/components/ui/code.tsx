import { FramePanel } from "@/components/ui/frame-panel";
import { cn } from "@/lib/utils";

/*
 * Code, dressed the way it looks where people actually write it: a tab with
 * the file name, a gutter of line numbers, a status bar, and a muted syntax
 * theme. The highlighters are deliberately small - they only need to color
 * the YAML and SQL this site shows, not parse either language.
 */

export type Lang = "yaml" | "sql" | "markdown" | "plain";
export type TokenKind =
  | "key"
  | "string"
  | "number"
  | "keyword"
  | "ref"
  | "comment"
  | "punct"
  | "heading"
  | "strong"
  | "emphasis"
  | "quote"
  | "text";
export type Token = { kind: TokenKind; text: string };

const TOKEN_CLASS: Record<TokenKind, string> = {
  key: "text-syn-key",
  string: "text-syn-string",
  number: "text-syn-number",
  keyword: "text-syn-keyword",
  ref: "text-syn-ref",
  comment: "text-ink-faint italic",
  punct: "text-ink-faint",
  heading: "text-syn-key font-bold",
  strong: "text-ink font-bold",
  emphasis: "text-ink-soft italic",
  quote: "text-ink-mute italic",
  text: "text-ink-soft",
};

const LANG_NAME: Record<Lang, string> = {
  yaml: "YAML",
  sql: "SQL",
  markdown: "Markdown",
  plain: "Plain Text",
};

/** A YAML scalar: numbers and durations, literals, quoted strings, name@version refs. */
function scalar(text: string): TokenKind {
  if (/^-?\d+(\.\d+)?[a-z]{0,2}$/.test(text)) return "number";
  if (/^(true|false|null|~)$/.test(text)) return "keyword";
  if (/^(["']).*\1$/.test(text)) return "string";
  if (/@\d+$/.test(text)) return "ref";
  return "text";
}

function yamlValue(value: string): Token[] {
  const list = value.match(/^\[(.*)\]$/);
  if (!list) return value ? [{ kind: scalar(value), text: value }] : [];
  const out: Token[] = [{ kind: "punct", text: "[" }];
  list[1].split(",").forEach((item, i) => {
    if (i > 0) out.push({ kind: "punct", text: "," });
    const lead = item.match(/^\s*/)![0];
    if (lead) out.push({ kind: "text", text: lead });
    const body = item.trim();
    if (body) out.push({ kind: scalar(body), text: body });
  });
  out.push({ kind: "punct", text: "]" });
  return out;
}

function tokenizeYaml(line: string): Token[] {
  if (/^\s*#/.test(line)) return [{ kind: "comment", text: line }];
  if (line.trim() === "---") return [{ kind: "punct", text: line }];

  const m = line.match(/^(\s*)(- )?(?:([A-Za-z_][\w. ]*?)(:)(\s*))?(.*)$/)!;
  const [, indent, dash, key, colon, gap, value] = m;
  const out: Token[] = [];
  if (indent) out.push({ kind: "text", text: indent });
  if (dash) out.push({ kind: "punct", text: dash });
  if (key) {
    out.push({ kind: "key", text: key }, { kind: "punct", text: colon });
    if (gap) out.push({ kind: "text", text: gap });
  }
  return [...out, ...yamlValue(value)];
}

const SQL_KEYWORDS = new Set([
  "select", "from", "where", "and", "or", "not", "in", "as", "join", "on",
  "group", "by", "order", "limit", "is", "null", "like", "between",
]);

function tokenizeSql(line: string): Token[] {
  const out: Token[] = [];
  const re = /('[^']*'?)|(\d+(?:\.\d+)?)|([A-Za-z_][\w.]*)|(--.*$)|([=<>!,*()]+)|(\s+)|(.)/g;
  for (const m of line.matchAll(re)) {
    const [text, str, num, word, comment, op] = m;
    out.push({
      text,
      kind: str
        ? "string"
        : num
          ? "number"
          : word
            ? SQL_KEYWORDS.has(word.toLowerCase())
              ? "keyword"
              : "text"
            : comment
              ? "comment"
              : op
                ? "punct"
                : "text",
    });
  }
  return out;
}

/** Inline markdown: **strong**, _emphasis_, and `code`, markers left visible. */
function inline(text: string, base: TokenKind = "text"): Token[] {
  const out: Token[] = [];
  // Underscores only count at word edges, so snake_case names stay whole.
  const re = /(\*\*)(.+?)(\*\*)|(?<!\w)(_)(.+?)(_)(?!\w)|(`)(.+?)(`)/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push({ kind: base, text: text.slice(last, m.index) });
    const [open, body, close, kind]: [string, string, string, TokenKind] = m[1]
      ? [m[1], m[2], m[3], "strong"]
      : m[4]
        ? [m[4], m[5], m[6], "emphasis"]
        : [m[7], m[8], m[9], "string"];
    out.push({ kind: "punct", text: open }, { kind, text: body }, { kind: "punct", text: close });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ kind: base, text: text.slice(last) });
  return out;
}

function tokenizeMarkdown(line: string): Token[] {
  const heading = line.match(/^(#{1,6} )(.*)$/);
  if (heading) {
    return [
      { kind: "heading", text: heading[1] },
      ...inline(heading[2], "heading"),
    ];
  }
  const quote = line.match(/^(> ?)(\[!\w+\])?(.*)$/);
  if (quote) {
    const out: Token[] = [{ kind: "punct", text: quote[1] }];
    if (quote[2]) out.push({ kind: "keyword", text: quote[2] });
    return [...out, ...inline(quote[3], "quote")];
  }
  const item = line.match(/^(\s*)([-*]|\d+\.)( )(.*)$/);
  if (item) {
    const out: Token[] = [];
    if (item[1]) out.push({ kind: "text", text: item[1] });
    return [
      ...out,
      { kind: "number", text: item[2] },
      { kind: "text", text: item[3] },
      ...inline(item[4]),
    ];
  }
  if (line.trim() === "---") return [{ kind: "punct", text: line }];
  return inline(line);
}

/**
 * How far a wrapped markdown line hangs, in characters, so a long list item
 * or quote wraps under its own text rather than under its marker.
 */
export function hangOf(line: string) {
  return line.match(/^(\s*(?:[-*]|\d+\.|>) (?:\[!\w+\] ?)?)/)?.[1].length ?? 0;
}

export function tokenize(line: string, lang: Lang): Token[] {
  if (lang === "yaml") return tokenizeYaml(line);
  if (lang === "sql") return tokenizeSql(line);
  if (lang === "markdown") return tokenizeMarkdown(line);
  return [{ kind: "text", text: line }];
}

/**
 * Renders tokens, optionally only the first `upto` characters - for code
 * being typed. The line is tokenized whole first, so a word half typed
 * already wears its final color, and the untyped rest holds its space so
 * nothing reflows as the text arrives.
 */
export function Tokens({
  tokens,
  upto,
  caret = false,
}: {
  tokens: Token[];
  upto?: number;
  caret?: boolean;
}) {
  let left = upto ?? Infinity;
  const typed: React.ReactNode[] = [];
  const rest: string[] = [];
  tokens.forEach((token, i) => {
    const n = Math.max(0, Math.min(token.text.length, left));
    left -= n;
    if (n > 0) {
      typed.push(
        <span key={i} className={TOKEN_CLASS[token.kind]}>
          {token.text.slice(0, n)}
        </span>
      );
    }
    if (n < token.text.length) rest.push(token.text.slice(n));
  });
  return (
    <>
      {typed}
      {caret && <Caret />}
      {rest.length > 0 && <span className="invisible">{rest.join("")}</span>}
    </>
  );
}

export function Syntax({ text, lang }: { text: string; lang: Lang }) {
  return <Tokens tokens={tokenize(text, lang)} />;
}

/** A zero-width text cursor, so it never nudges the line it sits in. */
export function Caret() {
  return (
    <span
      aria-hidden
      className="-mr-px inline-block h-[1.15em] w-0 animate-pulse border-l border-ink align-[-0.2em]"
    />
  );
}

/** One numbered line. `active` is the editor's current-line highlight. */
export function CodeRow({
  n,
  active = false,
  hang,
  className,
  children,
}: {
  n: number;
  active?: boolean;
  /** Soft-wrap the line, hanging wrapped text this many characters in. */
  hang?: number;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-[2.25rem_minmax(0,1fr)] transition-colors",
        active && "bg-accent-pale/70",
        className
      )}
    >
      <span
        aria-hidden
        className={cn(
          "pr-3 text-right tabular-nums select-none",
          active ? "text-ink-soft" : "text-ink-faint/70"
        )}
      >
        {n}
      </span>
      <span
        className={cn(
          "min-h-[1.75em] pr-4",
          hang === undefined ? "whitespace-pre" : "whitespace-pre-wrap break-words"
        )}
        style={hang ? { paddingLeft: `${hang}ch`, textIndent: `-${hang}ch` } : undefined}
      >
        {children}
      </span>
    </div>
  );
}

/** The strip of window controls and open tabs across the top of an editor. */
export function EditorTabs({
  tabs,
  active = 0,
  meta,
  controls = true,
}: {
  tabs: string[];
  active?: number;
  meta?: React.ReactNode;
  controls?: boolean;
}) {
  return (
    <div className="flex items-stretch border-b border-rule bg-paper-warm/60">
      {controls && (
        <span aria-hidden className="flex items-center gap-1.5 px-3.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="size-[7px] rounded-full border border-rule" />
          ))}
        </span>
      )}
      <div className="flex min-w-0 overflow-hidden">
        {tabs.map((tab, i) => (
          <span
            key={tab}
            className={cn(
              "flex items-center gap-2 border-r border-rule px-3.5 py-2 font-mono text-[0.6875rem] whitespace-nowrap",
              i === active
                ? "relative -mb-px bg-editor text-ink before:absolute before:inset-x-0 before:top-0 before:h-px before:bg-accent"
                : "text-ink-faint"
            )}
          >
            {tab}
            {i === active && (
              <span aria-hidden className="text-ink-faint">
                &times;
              </span>
            )}
          </span>
        ))}
      </div>
      {meta && (
        <span className="kicker ml-auto flex items-center px-4 !text-[0.5625rem]">
          {meta}
        </span>
      )}
    </div>
  );
}

/** The thin bar along the bottom of an editor. */
export function StatusBar({
  left,
  right,
}: {
  left?: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-t border-rule bg-paper-warm/60 px-3.5 py-1 font-mono text-[0.625rem] text-ink-faint">
      <span className="truncate">{left}</span>
      <span className="flex shrink-0 gap-4">{right}</span>
    </div>
  );
}

/** Status items an editor shows for a file in `lang`. */
export function fileStatus(lang: Lang) {
  return (
    <>
      <span>Spaces: 2</span>
      <span className="hidden sm:inline">UTF-8</span>
      <span>{LANG_NAME[lang]}</span>
    </>
  );
}

/**
 * A complete, static editor window around one file. `framed` gives it the
 * site's registration-mark panel; unframed it sits inside another panel.
 */
export function CodeBlock({
  code,
  lang,
  filename,
  meta,
  framed = false,
  status = true,
  className,
}: {
  code: string;
  lang: Lang;
  filename: string;
  meta?: React.ReactNode;
  framed?: boolean;
  status?: boolean;
  className?: string;
}) {
  const lines = code.split("\n");
  const body = (
    <>
      <EditorTabs tabs={[filename]} meta={meta} />
      <div
        className={cn(
          "overflow-x-auto bg-editor py-2.5 font-mono leading-[1.75]",
          lang === "markdown" ? "text-[0.75rem]" : "text-[0.6875rem]"
        )}
      >
        {lines.map((line, i) => (
          <CodeRow
            key={i}
            n={i + 1}
            hang={lang === "markdown" ? hangOf(line) : undefined}
          >
            <Syntax text={line} lang={lang} />
          </CodeRow>
        ))}
      </div>
      {status && (
        <StatusBar
          left={`Ln ${lines.length}, Col ${lines[lines.length - 1].length + 1}`}
          right={fileStatus(lang)}
        />
      )}
    </>
  );

  return framed ? (
    <FramePanel className={cn("bg-editor", className)}>{body}</FramePanel>
  ) : (
    <div className={cn("border border-rule bg-editor", className)}>{body}</div>
  );
}

function WindowDots() {
  return (
    <span aria-hidden className="flex shrink-0 gap-1.5">
      {[0, 1, 2].map((i) => (
        <span key={i} className="size-[7px] rounded-full border border-rule" />
      ))}
    </span>
  );
}

/**
 * A window's title bar: controls on the left, the title centered, and an
 * optional note or control on the right. Terminals and the command bar
 * of a split editor use it.
 */
export function WindowBar({
  title,
  meta,
}: {
  title: React.ReactNode;
  meta?: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[3rem_minmax(0,1fr)_auto] items-center gap-3 border-b border-rule bg-paper-warm/60 py-2 pr-4 pl-3.5">
      <WindowDots />
      <span className="truncate text-center font-mono text-[0.625rem] text-ink-faint">
        {title}
      </span>
      <span className="flex min-w-[3rem] justify-end font-mono text-[0.625rem] text-ink-faint">
        {meta}
      </span>
    </div>
  );
}

/** A browser's toolbar, for the things a run produces as web pages. */
export function BrowserBar({
  url,
  meta,
}: {
  url: string;
  meta?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 border-b border-rule bg-paper-warm/60 py-2 pr-4 pl-3.5">
      <WindowDots />
      <span className="flex min-w-0 flex-1 items-center gap-2 border border-rule bg-editor px-2.5 py-1 font-mono text-[0.625rem]">
        <span aria-hidden className="text-ink-faint">
          file://
        </span>
        <span className="truncate text-ink-soft">{url}</span>
      </span>
      {meta && (
        <span className="kicker shrink-0 !text-[0.5625rem]">{meta}</span>
      )}
    </div>
  );
}

/**
 * Lines of the machine's own output, set in a strip of editor ground: the
 * first word - the verb or the subject - picks up the syntax color, the
 * rest stays quiet. For the short log lines that close out a card.
 */
export function OutputLines({
  lines,
  className,
}: {
  lines: readonly string[];
  className?: string;
}) {
  return (
    <div className={cn("space-y-1 bg-editor font-mono text-[0.6875rem] leading-relaxed", className)}>
      {lines.map((line) => {
        const [, head, rest] = line.match(/^(\S+)(.*)$/) ?? [, line, ""];
        return (
          <p key={line} className="break-words">
            <span aria-hidden className="text-ink-faint select-none">
              &gt;{" "}
            </span>
            <span className="text-syn-key">{head}</span>
            <span className="text-ink-mute">{rest}</span>
          </p>
        );
      })}
    </div>
  );
}
