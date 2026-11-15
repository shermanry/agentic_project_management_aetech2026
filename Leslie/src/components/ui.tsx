import { useState, type CSSProperties, type ReactNode } from "react";
import {
  CATEGORIES,
  CAT,
  type GraphNode,
  type NodeKind,
} from "../data/sampleProject";
import { EXAMPLES } from "../features/ask";
import { colorOf, toneOf, useGraph } from "../model/graph";

const PATHS: Record<NodeKind | "inbox", string> = {
  document: "M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6",
  site: "M3 20l6-14 6 9 3-4 3 9zM3 20h18",
  model: "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5",
  constraint: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  weather: "M7 18h10a4 4 0 0 0 0-8 6 6 0 0 0-11.5 1.5A3.3 3.3 0 0 0 7 18z",
  decision: "M12 3l9 9-9 9-9-9z",
  output: "M4 4h16v12H4zM8 20h8M12 16v4",
  note: "M5 4h14v12l-4 4H5zM15 20v-4h4M8 9h8M8 13h5",
  file: "M6 3h8l4 4v14H6zM14 3v4h4",
  inbox: "M3 13l3-8h12l3 8v6H3zM3 13h5l1 2h6l1-2h5",
};

export function Icon({
  kind,
  size = 16,
}: {
  kind: NodeKind | "inbox";
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d={PATHS[kind]} />
    </svg>
  );
}

export function Badge({ status }: { status: string }) {
  return <span className={`badge t-${toneOf(status)}`}>{status}</span>;
}

export function CatDot({ node, size = 9 }: { node: GraphNode; size?: number }) {
  return (
    <span
      className="catdot"
      style={{ width: size, height: size, background: colorOf(node) }}
    />
  );
}

export function CatLabel({ node }: { node: GraphNode }) {
  return (
    <span className="catlabel">
      <CatDot node={node} />
      {node.category ? CAT[node.category].label : "Unclassified"}
    </span>
  );
}

export function Legend({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`legend ${compact ? "compact" : ""}`}>
      {CATEGORIES.map((c) => (
        <span key={c.id} title={c.purpose}>
          <i style={{ background: c.color }} />
          {c.label}
        </span>
      ))}
    </div>
  );
}

/**
 * Ask bar, shared by PM and Expert. Type a question in plain words; the guide answers briefly and
 * points to the matching nodes. Enter opens the best match.
 */
export function SearchBar({ id }: { id: string }) {
  const { state, dispatch, matches, guide, byId } = useGraph();
  const hits = state.nodes.filter(matches);
  const active = state.query.trim() !== "" || state.filter !== "all";
  const ranked = guide
    ? guide.ids.map(byId).filter((n): n is GraphNode => !!n && matches(n))
    : [];
  return (
    <div className="ask-wrap">
      <form
        className="ed-search"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          const first = ranked[0] ?? hits[0];
          if (first) dispatch({ type: "select", id: first.id });
        }}
      >
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          aria-hidden
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M16.5 16.5L21 21" />
        </svg>
        <input
          id={id}
          type="search"
          aria-label="Ask a question about the project"
          placeholder="Ask anything about the project"
          value={state.query}
          onChange={(e) =>
            dispatch({ type: "setQuery", query: e.target.value })
          }
          autoComplete="off"
        />
        {active && (
          <span className="ed-meta count">
            {hits.length} of {state.nodes.length}
          </span>
        )}
        {state.query && (
          <button
            type="button"
            className="clear"
            aria-label="Clear question"
            onClick={() => dispatch({ type: "setQuery", query: "" })}
          >
            ×
          </button>
        )}
      </form>

      {guide ? (
        <div className="ask-answer" aria-live="polite">
          <p title={guide.answer}>{guide.answer}</p>
          <div className="ask-go">
            {ranked.length > 0 && <span className="ed-meta">Go to</span>}
            {ranked.slice(0, 5).map((n) => (
              <button
                key={n.id}
                className={`ask-chip ${n.id === state.selectedId ? "on" : ""}`}
                onClick={() => dispatch({ type: "select", id: n.id })}
              >
                <CatDot node={n} />
                {n.title}
              </button>
            ))}
            <span className="ed-meta note">
              Guide · sample logic, not a live AI
            </span>
          </div>
        </div>
      ) : (
        <div className="ask-try">
          <span className="ed-meta">Try</span>
          {EXAMPLES.slice(0, 4).map((q) => (
            <button
              key={q}
              onClick={() => dispatch({ type: "setQuery", query: q })}
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** The top row shared by the PM and Expert tabs: ask bar plus a large "Add node" button. */
export function AskRow({ id, onAdded }: { id: string; onAdded?: () => void }) {
  const { dispatch } = useGraph()
  const [note, setNote] = useState<string>()
  return (
    <>
      <div className="pm-search">
        <SearchBar id={id} />
        <button className="ed-cta" onClick={() => setNote(note === undefined ? '' : undefined)} aria-expanded={note !== undefined}>
          + Add node
        </button>
      </div>
      {note !== undefined && (
        <form
          className="pm-add"
          onSubmit={(e) => {
            e.preventDefault()
            if (note.trim()) dispatch({ type: 'addNode', title: note.trim(), kind: 'note' })
            setNote(undefined)
            onAdded?.()
          }}
        >
          <input id={`${id}-new`} autoFocus aria-label="New node title" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Name the new node" />
          <button className="ed-link plain" disabled={!note.trim()}>
            Add
          </button>
          <button type="button" className="ed-link dim" onClick={() => setNote(undefined)}>
            Cancel
          </button>
          <span className="ed-meta">Waits to be placed until you accept where it goes</span>
        </form>
      )}
    </>
  )
}

/** Category filter chips, shared by PM and Expert. */
export function CategoryChips() {
  const { state, dispatch } = useGraph();
  const f = state.filter;
  const inbox = state.nodes.filter(
    (n) => n.category === null || n.status === "Unclassified",
  ).length;
  return (
    <div className="chips" role="group" aria-label="Filter by category">
      <button
        className={`fchip ${f === "all" ? "on" : ""}`}
        onClick={() => dispatch({ type: "setFilter", filter: "all" })}
      >
        All <span>{state.nodes.length}</span>
      </button>
      {CATEGORIES.map((c) => (
        <button
          key={c.id}
          className={`fchip ${f === c.id ? "on" : ""}`}
          style={{ "--c": c.color } as CSSProperties}
          onClick={() =>
            dispatch({ type: "setFilter", filter: f === c.id ? "all" : c.id })
          }
        >
          <i />
          {c.label}{" "}
          <span>{state.nodes.filter((n) => n.category === c.id).length}</span>
        </button>
      ))}
      <button
        className={`fchip dashed ${f === "unclassified" ? "on" : ""}`}
        onClick={() =>
          dispatch({
            type: "setFilter",
            filter: f === "unclassified" ? "all" : "unclassified",
          })
        }
      >
        Unclassified <span>{inbox}</span>
      </button>
    </div>
  );
}

export function Panel({
  title,
  right,
  className = "",
  children,
}: {
  title: string;
  right?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-h">
        <h2>{title}</h2>
        {right}
      </header>
      {children}
    </section>
  );
}

/** Prewritten, graph-derived answer. Clearly labelled: there is no live AI behind it. */
function cannedAnswer(q: string, n: GraphNode, related: GraphNode[]) {
  const open = [n, ...related].filter((x) => x.openQuestion);
  return `From the graph: "${n.title}" connects to ${related.length} node${related.length === 1 ? "" : "s"} (${
    related.map((r) => r.title).join(", ") || "none"
  }). ${open.length ? `Open items: ${open.map((x) => x.openQuestion).join(" ")}` : "No open verifications on this neighborhood."}${
    q.toLowerCase().includes("when")
      ? " Scheduling depends on the weather window and survey schedule nodes, both sample data."
      : ""
  }`;
}

export function NodeInspector({
  compact = false,
  onClose,
  jump,
}: {
  compact?: boolean;
  onClose?: () => void;
  jump?: { label: string; hash: string };
}) {
  const { state, dispatch, byId, edgesOf, pendingFor } = useGraph();
  const n = byId(state.selectedId);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<{ id: string; text: string }>();
  if (!n)
    return (
      <div className="inspector empty">
        Select a node to see what it is, why it matters and how it connects.
      </div>
    );
  const edges = edgesOf(n.id);
  const related = edges
    .map((e) => byId(e.source === n.id ? e.target : e.source)!)
    .filter(Boolean);
  const pending = pendingFor(n.id);
  const resolved = state.candidates.filter(
    (c) => c.state !== "pending" && (c.source === n.id || c.target === n.id),
  );

  return (
    <div className={`inspector ${compact ? "compact" : ""}`}>
      <div className="ins-head">
        <div className="ins-kicker">
          <CatLabel node={n} />
          <span className="dim">· {n.kind}</span>
          {onClose && (
            <button
              className="icon-btn"
              onClick={onClose}
              aria-label="Close inspector"
            >
              ×
            </button>
          )}
        </div>
        <h3 className="ins-title">{n.title}</h3>
        <div className="ins-badges">
          <Badge status={n.status} />
          <span className="dim small">
            {edges.length} relationship{edges.length === 1 ? "" : "s"}
          </span>
        </div>
        {jump && (
          <button
            className="ed-link jump"
            onClick={() => (location.hash = jump.hash)}
          >
            {jump.label}
          </button>
        )}
      </div>

      <section className="ins-sec">
        <h4>What this is</h4>
        <p>{n.summary}</p>
      </section>
      {!compact && (
        <section className="ins-sec">
          <h4>Why it matters</h4>
          <p>{n.why}</p>
        </section>
      )}
      <section className="ins-sec">
        <dl className="specs">
          <dt>Source</dt>
          <dd>{n.origin.name}</dd>
          <dt>Owner</dt>
          <dd>{n.owner}</dd>
          <dt>Verification</dt>
          <dd>{n.verification}</dd>
          {!compact && (
            <>
              <dt>Updated</dt>
              <dd className="mono">{n.updatedAt ?? "not set"}</dd>
            </>
          )}
        </dl>
        {n.openQuestion && <div className="open-q">{n.openQuestion}</div>}
      </section>

      <section className="ins-sec">
        <h4>Connected nodes</h4>
        {edges.length ? (
          <ul className="rels">
            {edges.map((e) => {
              const out = e.source === n.id;
              const other = byId(out ? e.target : e.source)!;
              return (
                <li key={e.id}>
                  <button
                    onClick={() => dispatch({ type: "select", id: other.id })}
                  >
                    <span className="rel-verb">
                      {out ? "→" : "←"} {e.relation}
                    </span>
                    <CatDot node={other} />
                    <span className="rel-t">{other.title}</span>
                    {e.status === "accepted" && (
                      <span className="badge t-ai">AI · accepted</span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="dim">No approved relationships yet.</p>
        )}
      </section>

      {(pending.length > 0 || resolved.length > 0) && (
        <section className="ins-sec ai-box">
          <h4>AI suggestions · need approval</h4>
          {pending.map((c) => (
            <div key={c.id} className="sugg">
              <div>
                <b>{byId(c.source)?.title}</b> <i>{c.relation}</i>{" "}
                <b>{byId(c.target)?.title}</b>
              </div>
              <div className="dim small">{c.reason}</div>
              <div className="sugg-act">
                <button
                  className="btn sm primary"
                  onClick={() => dispatch({ type: "accept", id: c.id })}
                >
                  Accept link
                </button>
                <button
                  className="btn sm"
                  onClick={() => dispatch({ type: "dismiss", id: c.id })}
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
          {resolved.map((c) => (
            <div key={c.id} className="sugg done dim small">
              {c.state === "accepted" ? "Accepted" : "Dismissed"}:{" "}
              {byId(c.source)?.title} {c.relation} {byId(c.target)?.title}
            </div>
          ))}
        </section>
      )}

      {!compact && (
        <section className="ins-sec">
          <h4>Ask about this node</h4>
          <form
            className="ask"
            onSubmit={(e) => {
              e.preventDefault();
              if (q.trim())
                setAnswer({ id: n.id, text: cannedAnswer(q, n, related) });
            }}
          >
            <input
              id="ask"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="e.g. What blocks this from approval?"
            />
            <button className="btn sm">Ask</button>
          </form>
          {answer?.id === n.id && (
            <div className="answer">
              <span className="badge t-muted">
                Concept · prewritten from graph, not live AI
              </span>
              <p>{answer.text}</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
