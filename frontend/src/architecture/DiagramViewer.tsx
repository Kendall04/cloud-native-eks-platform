import { useState, useEffect, useRef } from "react";
import type { DiagramId } from "./catalog";
import pins from "../../architecture-pins.json";
import hashes, { assetUrls } from "virtual:architecture-integrity";
type ReadingGuide = {
  chapters: { id: string; label: string; focus: string[]; note: string }[];
  nodes: {
    id: string;
    label: string;
    description: string;
    sources: string[];
  }[];
  connections: {
    id: string;
    from: string;
    to: string;
    label: string;
    note: string;
    classification: string;
  }[];
  evidence: { title: string; items: string[] }[];
};
export function DiagramViewer({ id, title }: { id: DiagramId; title: string }) {
  const [resource, setResource] = useState<{
    id: string;
    html?: string;
    guide?: ReadingGuide;
    error?: string;
  }>();
  const [expanded, setExpanded] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [retry, setRetry] = useState(0);
  const [fullscreenError, setFullscreenError] = useState("");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [chapterIndex, setChapterIndex] = useState(0);
  const [step, setStep] = useState(0);
  const [readingStarted, setReadingStarted] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const expandButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    function change() {
      setIsFullscreen(document.fullscreenElement === container.current);
    }
    function escape(event: KeyboardEvent) {
      if (
        event.key === "Escape" &&
        document.fullscreenElement === container.current
      ) {
        event.preventDefault();
        void document.exitFullscreen();
      }
    }
    document.addEventListener("fullscreenchange", change);
    window.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("fullscreenchange", change);
      window.removeEventListener("keydown", escape);
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setResource({ id, error: "Diagram loading timed out. Please retry." });
      controller.abort();
    }, 15000);
    fetch(assetUrls[id], {
      signal: controller.signal,
      credentials: "omit",
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Diagram could not be loaded.");
        const value = await response.json();
        if (
          value.schemaVersion !== 1 ||
          value.name !== id ||
          value.originalSha256 !== pins[id] ||
          typeof value.html !== "string" ||
          !value.html.includes('http-equiv="Content-Security-Policy"')
        )
          throw new Error("Diagram integrity check failed.");
        const digest = await crypto.subtle.digest(
          "SHA-256",
          new TextEncoder().encode(value.html),
        );
        const hex = [...new Uint8Array(digest)]
          .map((n) => n.toString(16).padStart(2, "0"))
          .join("");
        if (hex !== value.presentationSha256 || hex !== hashes[id])
          throw new Error("Diagram integrity check failed.");
        if (!controller.signal.aborted)
          setResource({ id, html: value.html, guide: value.guide });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setResource({
            id,
            error:
              error instanceof Error ? error.message : "Diagram unavailable.",
          });
      })
      .finally(() => clearTimeout(timer));
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [id, retry]);
  useEffect(() => {
    if (!expanded) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const excluded: HTMLElement[] = [];
    let branch: HTMLElement | null = container.current;
    while (branch?.parentElement) {
      for (const sibling of branch.parentElement.children) {
        if (
          sibling !== branch &&
          sibling instanceof HTMLElement &&
          !sibling.inert
        ) {
          sibling.setAttribute("inert", "");
          excluded.push(sibling);
        }
      }
      branch = branch.parentElement;
    }
    expandButton.current?.focus();
    function key(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (document.fullscreenElement) return;
        setExpanded(false);
        expandButton.current?.focus();
      }
    }
    window.addEventListener("keydown", key);
    return () => {
      for (const element of excluded) element.removeAttribute("inert");
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", key);
    };
  }, [expanded]);
  useEffect(() => {
    function closeMessage(event: MessageEvent) {
      if (
        event.source === frame.current?.contentWindow &&
        event.origin === "null" &&
        event.data !== null &&
        typeof event.data === "object" &&
        Object.keys(event.data).length === 1 &&
        event.data.type === "archify-viewer-escape"
      ) {
        if (document.fullscreenElement === container.current) {
          void document.exitFullscreen();
          return;
        }
        setExpanded(false);
        expandButton.current?.focus();
      }
    }
    window.addEventListener("message", closeMessage);
    return () => window.removeEventListener("message", closeMessage);
  }, []);
  const current = resource?.id === id ? resource : undefined;
  const guide = current?.guide;
  const chapter = guide?.chapters[chapterIndex];
  const selected = guide?.nodes.find(
    (node) => node.id === chapter?.focus[step],
  );
  function focusNode(nodeId: string | undefined) {
    setReadingStarted(true);
    if (nodeId)
      frame.current?.contentWindow?.postMessage(
        { type: "archify-focus-node", id: nodeId },
        "*",
      );
  }
  function readStep(index: number) {
    setStep(index);
    focusNode(chapter?.focus[index]);
  }
  async function fullscreen() {
    setFullscreenError("");
    try {
      if (document.fullscreenElement === container.current) {
        await document.exitFullscreen();
        return;
      }
      if (!container.current?.requestFullscreen)
        throw new Error("Fullscreen unavailable");
      await container.current.requestFullscreen();
    } catch {
      setFullscreenError(
        "Native fullscreen is unavailable. Use Expand view instead.",
      );
    }
  }
  return (
    <div
      ref={container}
      className={"diagram-viewer" + (expanded ? " is-expanded" : "")}
      role={expanded ? "dialog" : undefined}
      aria-modal={expanded ? true : undefined}
      aria-label={title + " viewer"}
    >
      <div className="viewer-toolbar">
        <strong>{title}</strong>
        <div>
          <button
            ref={expandButton}
            title="Focus on the diagram without the surrounding page"
            aria-pressed={expanded}
            onClick={() => {
              setExpanded((v) => !v);
            }}
          >
            {expanded ? "Close expanded view" : "Expand view"}
          </button>
          <button onClick={fullscreen}>
            {isFullscreen ? "Exit fullscreen" : "Fullscreen"}
          </button>
        </div>
      </div>
      {fullscreenError && <p role="status">{fullscreenError}</p>}
      {!current && (
        <p className="loading" role="status">
          Loading interactive diagram…
        </p>
      )}
      {current?.error && (
        <div role="alert" className="error">
          {current.error}{" "}
          <button onClick={() => setRetry((v) => v + 1)}>Retry diagram</button>
        </div>
      )}
      {current?.html && (
        <>
          {guide && chapter && selected && (
            <section
              className="diagram-reader"
              aria-label="Guided diagram reading"
            >
              {!readingStarted && (
                <p className="reader-intro">
                  <strong>Start here: guided reading.</strong> Choose a chapter,
                  then follow its components one step at a time. The complete
                  map stays available below.
                </p>
              )}
              <div className="reader-controls">
                <label>
                  Chapter · Reading tour
                  <select
                    value={chapterIndex}
                    onChange={(event) => {
                      const index = Number(event.target.value);
                      setChapterIndex(index);
                      setStep(0);
                      focusNode(guide.chapters[index].focus[0]);
                    }}
                  >
                    {guide.chapters.map((item, index) => (
                      <option key={item.id} value={index}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  disabled={!readingStarted || step === 0}
                  onClick={() => readStep(step - 1)}
                >
                  Previous component
                </button>
                <button
                  disabled={
                    !readingStarted || step === chapter.focus.length - 1
                  }
                  onClick={() => readStep(step + 1)}
                >
                  Next component
                </button>
                <button
                  className="reader-start"
                  onClick={() => focusNode(selected.id)}
                >
                  {readingStarted
                    ? "Focus selected component"
                    : "Start guided tour"}
                </button>
              </div>
              {readingStarted && (
                <div
                  className="reader-detail"
                  aria-live="polite"
                  aria-atomic="true"
                >
                  <h2>
                    Step {step + 1} / {chapter.focus.length} · Component:{" "}
                    {selected.label}
                  </h2>
                  <p>
                    {selected.description}. {chapter.note}
                  </p>
                  <ul>
                    {guide.connections
                      .filter(
                        (edge) =>
                          edge.from === selected.id || edge.to === selected.id,
                      )
                      .map((edge) => (
                        <li key={edge.id}>
                          <span className="evidence-class">
                            {edge.classification}
                          </span>{" "}
                          {
                            guide.nodes.find((node) => node.id === edge.from)
                              ?.label
                          }{" "}
                          →{" "}
                          {
                            guide.nodes.find((node) => node.id === edge.to)
                              ?.label
                          }
                          : {edge.label}. {edge.note}
                        </li>
                      ))}
                  </ul>
                </div>
              )}
            </section>
          )}
          <iframe
            ref={frame}
            key={id}
            title={title + " interactive diagram"}
            srcDoc={current.html}
            sandbox="allow-scripts allow-downloads"
            referrerPolicy="no-referrer"
            allow="clipboard-write 'none'; camera 'none'; microphone 'none'; geolocation 'none'"
            onLoad={() => setLoaded(true)}
            onError={() =>
              setResource({ id, error: "The diagram failed to render." })
            }
          />
          {!loaded && <p role="status">Preparing interactive controls…</p>}
          {guide && (
            <details className="diagram-transcript">
              <summary>Complete text alternative, sources and evidence</summary>
              <p>
                Connections are DECLARED design, not a live trace. OBSERVED and
                PROVEN statements below are dated; UNVERIFIED limits remain
                explicit.
              </p>
              {guide.nodes.map((node) => (
                <section key={node.id}>
                  <h3>{node.label}</h3>
                  <p>{node.description}</p>
                  <ul>
                    {guide.connections
                      .filter((edge) => edge.from === node.id)
                      .map((edge) => (
                        <li key={edge.id}>
                          {edge.classification}: {node.label} →{" "}
                          {
                            guide.nodes.find((target) => target.id === edge.to)
                              ?.label
                          }
                          : {edge.label}. {edge.note}
                        </li>
                      ))}
                  </ul>
                  <p className="reader-sources">
                    Source: {node.sources.join(" · ")}
                  </p>
                </section>
              ))}
              {guide.evidence.map((item) => (
                <section key={item.title}>
                  <h3>{item.title}</h3>
                  <ul>
                    {item.items.map((text) => (
                      <li key={text}>{text}</li>
                    ))}
                  </ul>
                </section>
              ))}
            </details>
          )}
        </>
      )}
      <p className="viewer-help">
        Fit all is a panoramic overview, not a reading-size view. Use the
        reading tour and Next component for guided focus. Fit width (W) enlarges
        tall diagrams; zoom and drag the background to explore. Search / · Reset
        0 · Escape returns from expanded view.
      </p>
    </div>
  );
}
