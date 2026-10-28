import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent, type UIEvent } from "react";
import type { ReviewJob } from "./types";
import "./HistoryStack.css";

type Props = {
  jobs: ReviewJob[];
  projectId: string;
  activeJobId?: string;
  languageFor: (job: ReviewJob) => string;
  onOpen: (job: ReviewJob) => void;
};

const ROW_HEIGHT = 68;
const HOLD_MS = 280;
const PULL_DISTANCE = 54;

export default function HistoryStack({ jobs, projectId, activeJobId, languageFor, onOpen }: Props) {
  const [topIndex, setTopIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [dragY, setDragY] = useState(0);
  const [scrollProgress, setScrollProgress] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const holdRef = useRef<{ pointerId: number; startY: number; active: boolean; timer: number } | null>(null);
  const suppressClick = useRef(false);

  useEffect(() => { setTopIndex(0); setExpanded(false); setDragY(0); }, [projectId]);
  useEffect(() => { if (expanded) suppressClick.current = false; }, [expanded]);
  useEffect(() => () => { if (holdRef.current) window.clearTimeout(holdRef.current.timer); }, []);
  useLayoutEffect(() => {
    if (expanded && scrollRef.current && jobs.length > 3) {
      scrollRef.current.scrollTop = jobs.length * ROW_HEIGHT;
    }
  }, [expanded, jobs.length]);

  if (!jobs.length) return <div className="history-stack-empty">当前项目还没有审查记录。</div>;

  const top = jobs[topIndex % jobs.length];
  const copies = jobs.length > 3 ? 3 : 1;
  const next = (direction: number) => setTopIndex((current) => (current + direction + jobs.length) % jobs.length);

  function endHold() {
    if (holdRef.current) window.clearTimeout(holdRef.current.timer);
    holdRef.current = null;
    setDragY(0);
  }

  function onCardDown(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    const pointerId = event.pointerId;
    const startY = event.clientY;
    const timer = window.setTimeout(() => {
      if (holdRef.current?.pointerId === pointerId) holdRef.current.active = true;
    }, HOLD_MS);
    holdRef.current = { pointerId, startY, active: false, timer };
    event.currentTarget.setPointerCapture(pointerId);
  }

  function onCardMove(event: PointerEvent<HTMLButtonElement>) {
    const hold = holdRef.current;
    if (!hold || hold.pointerId !== event.pointerId || !hold.active) return;
    const distance = Math.max(0, event.clientY - hold.startY);
    setDragY(Math.min(distance, 88));
    if (distance >= PULL_DISTANCE) {
      suppressClick.current = true;
      endHold();
      setExpanded(true);
    }
  }

  function onCardUp(event: PointerEvent<HTMLButtonElement>) {
    if (holdRef.current?.pointerId !== event.pointerId) return;
    endHold();
  }

  function onListScroll(event: UIEvent<HTMLDivElement>) {
    const element = event.currentTarget;
    const height = jobs.length * ROW_HEIGHT;
    if (copies === 3) {
      if (element.scrollTop < height * 0.35) element.scrollTop += height;
      else if (element.scrollTop > height * 1.65) element.scrollTop -= height;
      setScrollProgress(((element.scrollTop % height) + height) % height / height);
    } else {
      const range = element.scrollHeight - element.clientHeight;
      setScrollProgress(range > 0 ? element.scrollTop / range : 0);
    }
  }

  return <section className="history-stack" aria-label="当前项目的审查记录">
    {expanded ? <div className="history-expanded">
      <div className="history-expanded-heading"><strong>全部记录</strong>
        <button type="button" onClick={() => setExpanded(false)}>收起</button></div>
      <div className="history-expanded-body">
        <div className="history-expanded-list" ref={scrollRef} onScroll={onListScroll} role="region" aria-label="可循环滚动的审查记录">
          {Array.from({ length: copies }, (_, copy) => jobs.map((item) => copy === 1 || copies === 1
            ? <button type="button" className={`history-expanded-row ${activeJobId === item.id ? "is-active" : ""}`}
                key={`${copy}-${item.id}`} onClick={() => onOpen(item)}>
                <span className="history-expanded-file">{item.filename === "project.codesentinel-bundle" ? "项目审查" : item.filename}</span>
                <span>{languageFor(item)} · {new Date(item.created_at).toLocaleDateString("zh-CN")}</span>
              </button>
            : <div className={`history-expanded-row ${activeJobId === item.id ? "is-active" : ""}`}
                key={`${copy}-${item.id}`} aria-hidden="true" onClick={() => onOpen(item)}>
                <span className="history-expanded-file">{item.filename === "project.codesentinel-bundle" ? "项目审查" : item.filename}</span>
                <span>{languageFor(item)} · {new Date(item.created_at).toLocaleDateString("zh-CN")}</span>
              </div>))}
        </div>
        <div className="history-scroll-rail" aria-hidden="true"><span style={{ top: `${scrollProgress * 82}%` }} /></div>
      </div>
    </div> : <>
      <div className="history-deck" aria-label={`第 ${topIndex + 1} 条，共 ${jobs.length} 条`}>
        {Array.from({ length: Math.min(Math.max(jobs.length, 2), 3) }, (_, depth) => {
          const item = jobs[(topIndex + depth) % jobs.length];
          return depth === 0 ? <button type="button" key={item.id} className={`history-deck-card is-front ${dragY ? "is-dragging" : ""}`}
              style={{ transform: `translateY(${dragY}px)` }}
              onPointerDown={onCardDown} onPointerMove={onCardMove} onPointerUp={onCardUp}
              onPointerCancel={endHold}
              onClick={() => { if (suppressClick.current) { suppressClick.current = false; return; } onOpen(item); }}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") { event.preventDefault(); next(1); }
                if (event.key === "ArrowUp") { event.preventDefault(); next(-1); }
              }}>
              <span className="history-deck-filename">{item.filename === "project.codesentinel-bundle" ? "项目审查" : item.filename}</span>
            </button> : <div key={`${depth}-${item.id}`} className={`history-deck-card is-behind depth-${depth}`} aria-hidden="true">
              <span>{depth === 1 ? languageFor(top) : languageFor(item)}</span>
            </div>;
        })}
      </div>
      <div className="history-stack-controls">
        <span>{topIndex + 1} / {jobs.length}</span>
        <button type="button" onClick={() => next(1)} disabled={jobs.length < 2} aria-label="下一条审查记录">下一张 ↓</button>
        <button type="button" onClick={() => setExpanded(true)}>展开全部</button>
      </div>
      <p className="history-stack-hint">长按卡片向下拖，查看全部记录</p>
    </>}
  </section>;
}
