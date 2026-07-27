// Tiny, dependency-free Markdown → HTML renderer for assistant answers,
// covering the subset the LLM emits (headings, emphasis, code, lists,
// blockquotes, tables, links, rules). Everything is HTML-escaped before any
// markup is added, so model output can never inject live HTML.
import { esc } from './util.js';

// -- Inline formatting -----------------------------------------------------
// Applied to already-escaped, code-free text. Order matters: longer markers
// (***  **) run before shorter ones (*) so they win the match.
function inlineFormat(s) {
  return s
    // [text](url) — only safe schemes; anything else is left as plain text.
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) =>
      /^(https?:\/\/|mailto:|\/|#)/i.test(url)
        ? `<a href="${url}" target="_blank" rel="noopener">${txt}</a>`
        : m)
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/(^|[\s.,;:!?(])_([^_]+)_(?=[\s.,;:!?)]|$)/g, '$1<em>$2</em>')
    .replace(/~~(.+?)~~/g, '<del>$1</del>');
}

// Escape, format, and (optionally) post-process the plain-text runs, leaving
// inline `code` spans verbatim. `transform` is only fed text that is not code,
// so e.g. citation markers inside a code span are never touched.
function inline(raw, transform) {
  return String(raw).split(/(`[^`\n]+`)/g).map((part) => {
    if (part.length >= 2 && part.startsWith('`') && part.endsWith('`')) {
      return `<code>${esc(part.slice(1, -1))}</code>`;
    }
    let html = inlineFormat(esc(part));
    return transform ? transform(html) : html;
  }).join('');
}

const indentOf = (line) => line.match(/^(\s*)/)[1].length;
const RE_LIST = /^\s*([-*+]|\d+[.)])\s+/;
const RE_HR = /^\s*([-*_])\s*(\1\s*){2,}$/;

function isTableSep(line) {
  return !!line && line.includes('|') && /^\s*\|?[-:\s|]*-[-:\s|]*\|?\s*$/.test(line);
}

// Does this line begin a new block? Used to stop paragraph accumulation.
function opensBlock(line, next) {
  return /^\s*(```+|~~~+)/.test(line)
    || /^#{1,6}\s+/.test(line)
    || /^\s*>/.test(line)
    || RE_LIST.test(line)
    || RE_HR.test(line)
    || (line.includes('|') && isTableSep(next));
}

const splitRow = (line) =>
  line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());

// GitHub-style pipe table: header row, separator row, then body rows.
function parseTable(lines, start, transform) {
  const head = splitRow(lines[start]);
  const aligns = splitRow(lines[start + 1]).map((c) => {
    const l = c.startsWith(':'), r = c.endsWith(':');
    return l && r ? 'center' : r ? 'right' : l ? 'left' : '';
  });
  let i = start + 2;
  const rows = [];
  while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
    rows.push(splitRow(lines[i]));
    i++;
  }
  const sty = (k) => (aligns[k] ? ` style="text-align:${aligns[k]}"` : '');
  const th = head.map((c, k) => `<th${sty(k)}>${inline(c, transform)}</th>`).join('');
  const body = rows.map((r) =>
    `<tr>${head.map((_, k) => `<td${sty(k)}>${inline(r[k] || '', transform)}</td>`).join('')}</tr>`).join('');
  return [`<table><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table>`, i];
}

// One list (ul/ol). Lines indented past the marker recurse as nested content.
function parseList(lines, start, transform) {
  const base = indentOf(lines[start]);
  const ordered = /^\s*\d+[.)]\s+/.test(lines[start]);
  const items = [];
  let i = start;
  while (i < lines.length) {
    const m = lines[i].match(/^\s*([-*+]|\d+[.)])\s+(.*)$/);
    if (!lines[i].trim() || indentOf(lines[i]) !== base || !m) break;
    const child = [];
    i++;
    // Absorb continuation/nested lines (indented deeper than the marker).
    while (i < lines.length && (!lines[i].trim() || indentOf(lines[i]) > base)) {
      if (!lines[i].trim() && !(lines[i + 1] && indentOf(lines[i + 1]) > base)) break;
      child.push(lines[i].slice(base + 2));
      i++;
    }
    let html = inline(m[2], transform);
    if (child.length) html += render(child.join('\n'), transform);
    items.push(`<li>${html}</li>`);
  }
  const tag = ordered ? 'ol' : 'ul';
  return [`<${tag}>${items.join('')}</${tag}>`, i];
}

function render(src, transform) {
  const lines = String(src).replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block — content is emitted verbatim (escaped, no inline rules).
    const fence = line.match(/^\s*(```+|~~~+)\s*([\w+-]*)\s*$/);
    if (fence) {
      const close = fence[1][0] === '`' ? /^\s*```+\s*$/ : /^\s*~~~+\s*$/;
      const buf = [];
      i++;
      while (i < lines.length && !close.test(lines[i])) buf.push(lines[i++]);
      i++; // skip closing fence
      const cls = fence[2] ? ` class="language-${fence[2]}"` : '';
      out.push(`<pre><code${cls}>${esc(buf.join('\n'))}</code></pre>`);
      continue;
    }

    if (!line.trim()) { i++; continue; }

    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) { out.push(`<h${h[1].length}>${inline(h[2].trim(), transform)}</h${h[1].length}>`); i++; continue; }

    if (RE_HR.test(line)) { out.push('<hr>'); i++; continue; }

    if (/^\s*>/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ''));
      out.push(`<blockquote>${render(buf.join('\n'), transform)}</blockquote>`);
      continue;
    }

    if (line.includes('|') && isTableSep(lines[i + 1])) {
      const [html, next] = parseTable(lines, i, transform);
      out.push(html); i = next; continue;
    }

    if (RE_LIST.test(line)) {
      const [html, next] = parseList(lines, i, transform);
      out.push(html); i = next; continue;
    }

    // Paragraph: gather until a blank line or the start of another block.
    const buf = [];
    while (i < lines.length && lines[i].trim() && !opensBlock(lines[i], lines[i + 1])) buf.push(lines[i++]);
    out.push(`<p>${inline(buf.join('\n'), transform).replace(/\n/g, '<br>')}</p>`);
  }
  return out.join('\n');
}

// Render Markdown `src` to safe HTML. `opts.inline` is an optional hook run over
// each escaped, non-code text run (chat.js uses it to insert citation chips).
export function renderMarkdown(src, opts = {}) {
  return render(src, opts.inline);
}
