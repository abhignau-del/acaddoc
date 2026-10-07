// Small reusable form pieces.
import type { ReactNode } from "react";
import { move, removeAt, replaceAt } from "./courseops";

export function Text({ label, value, onChange, placeholder, wide }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; wide?: boolean;
}) {
  return (
    <label className={wide ? "field wide" : "field"}>
      <span>{label}</span>
      <input value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export function Num({ label, value, onChange, optional }: {
  label: string; value: number | null | undefined; onChange: (v: number | null) => void; optional?: boolean;
}) {
  return (
    <label className="field num">
      <span>{label}</span>
      <input
        type="number" min={0} inputMode="numeric"
        value={value ?? ""}
        placeholder={optional ? "–" : "0"}
        onChange={(e) => {
          const t = e.target.value;
          onChange(t === "" ? (optional ? null : 0) : Math.max(0, Math.trunc(Number(t))));
        }}
      />
    </label>
  );
}

export function Area({ value, onChange, placeholder, rows = 2, label }: {
  value: string; onChange: (v: string) => void; placeholder?: string; rows?: number; label?: string;
}) {
  return (
    <textarea aria-label={label ?? placeholder} rows={rows} value={value} placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)} />
  );
}

/** Up / down / remove buttons for one list entry. */
export function RowTools<T>({ list, i, set, what }: { list: T[]; i: number; set: (l: T[]) => void; what: string }) {
  return (
    <span className="rowtools">
      <button type="button" title={`Move ${what} up`} aria-label={`Move ${what} up`} disabled={i === 0}
        onClick={() => set(move(list, i, -1))}>↑</button>
      <button type="button" title={`Move ${what} down`} aria-label={`Move ${what} down`} disabled={i === list.length - 1}
        onClick={() => set(move(list, i, 1))}>↓</button>
      <button type="button" title={`Remove ${what}`} aria-label={`Remove ${what}`} className="danger"
        onClick={() => set(removeAt(list, i))}>✕</button>
    </span>
  );
}

/** An ordered list of text entries; numbering is shown, never typed. */
export function StringList({ items, onChange, mark, placeholder, what, rows = 1 }: {
  items: string[]; onChange: (l: string[]) => void; mark: (i: number) => string;
  placeholder: string; what: string; rows?: number;
}) {
  return (
    <div className="list">
      {items.map((s, i) => (
        <div className="list-row" key={i}>
          <span className="mark">{mark(i)}</span>
          {rows > 1
            ? <Area rows={rows} value={s} placeholder={placeholder} label={`${what} ${mark(i)}`}
                onChange={(v) => onChange(replaceAt(items, i, v))} />
            : <input aria-label={`${what} ${mark(i)}`} value={s} placeholder={placeholder}
                onChange={(e) => onChange(replaceAt(items, i, e.target.value))} />}
          <RowTools list={items} i={i} set={onChange} what={what} />
        </div>
      ))}
      <button type="button" className="add" onClick={() => onChange([...items, ""])}>+ Add {what}</button>
    </div>
  );
}

export function Section({ id, title, count, children }: { id: string; title: string; count?: number; children: ReactNode }) {
  return (
    <section id={`sec-${id}`} className="card">
      <h2>{title}{count ? <span className="badge">{count}</span> : null}</h2>
      {children}
    </section>
  );
}
