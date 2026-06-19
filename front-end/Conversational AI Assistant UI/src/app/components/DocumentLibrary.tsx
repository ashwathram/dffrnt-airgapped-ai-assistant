import { useState, useRef, useEffect } from "react";
import {
  FileText, FileSpreadsheet, File, Search,
  Upload, MoreHorizontal, Trash2, Settings2, Folder, Pencil, Check, X, Database,
} from "lucide-react";
import { Document, Tag, TagType } from "../types";
import { TagPill } from "./TagPill";
import { UploadModal } from "./UploadModal";
import { TagManagerModal } from "./TagManagerModal";

interface DocumentLibraryProps {
  documents: Document[];
  tags: Tag[];
  tagTypes: TagType[];
  onDocumentsChange: (docs: Document[]) => void;
  onTagsChange: (tags: Tag[]) => void;
  onTagTypesChange: (types: TagType[]) => void;
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  pdf: <FileText size={14} />,
  xlsx: <FileSpreadsheet size={14} />,
  docx: <File size={14} />,
  txt: <File size={14} />,
};
const TYPE_COLORS: Record<string, string> = {
  pdf: "#E72300",
  xlsx: "#0a7c4a",
  docx: "#0369a1",
  txt: "#5a6a78",
};
const TYPE_LABELS: Record<string, string> = {
  pdf: "PDF",
  xlsx: "XLSX",
  docx: "DOCX",
  txt: "TXT",
};

function TagEditor({ doc, tags, tagTypes, onSave, onClose }: {
  doc: Document;
  tags: Tag[];
  tagTypes: TagType[];
  onSave: (tagIds: string[]) => void;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState<string[]>([...doc.tagIds]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  const toggle = (id: string) =>
    setSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  return (
    <div ref={ref} className="absolute left-0 top-full mt-1 z-30 w-72 rounded-xl border border-border shadow-xl overflow-hidden" style={{ background: "var(--card)" }}>
      <div className="px-4 py-2 border-b border-border flex items-center justify-between">
        <span className="text-xs font-medium text-foreground">Edit tags</span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => { onSave(selected); onClose(); }}
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-white"
            style={{ background: "var(--primary)" }}
          >
            <Check size={11} /> Save
          </button>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-muted text-muted-foreground transition-colors">
            <X size={13} />
          </button>
        </div>
      </div>
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1 px-4 py-2 border-b border-border bg-muted/30">
          {selected.map((id) => {
            const tag = tags.find((t) => t.id === id);
            if (!tag) return null;
            const tt = tagTypes.find((t) => t.id === tag.typeId);
            return <TagPill key={id} tag={tag} tagType={tt} size="sm" onRemove={() => toggle(id)} />;
          })}
        </div>
      )}
      <div className="max-h-56 overflow-y-auto divide-y divide-border" style={{ scrollbarWidth: "thin" }}>
        {tagTypes.map((tt) => {
          const typeTags = tags.filter((t) => t.typeId === tt.id);
          if (typeTags.length === 0) return null;
          return (
            <div key={tt.id} className="px-4 py-2">
              <div className="flex items-center gap-1.5 mb-2">
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: tt.color }} />
                <span className="text-xs font-medium text-muted-foreground">{tt.name}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {typeTags.map((tag) => (
                  <button
                    key={tag.id}
                    onClick={() => toggle(tag.id)}
                    className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium transition-all"
                    style={{
                      background: selected.includes(tag.id) ? tt.color : `${tt.color}15`,
                      color: selected.includes(tag.id) ? "#fff" : tt.color,
                      border: `1px solid ${tt.color}40`,
                    }}
                  >
                    {tag.name}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DocRow({ doc, tags, tagTypes, onDelete, onUpdateTags, onUpdateDescription }: {
  doc: Document;
  tags: Tag[];
  tagTypes: TagType[];
  onDelete: () => void;
  onUpdateTags: (tagIds: string[]) => void;
  onUpdateDescription: (desc: string) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [editingTags, setEditingTags] = useState(false);
  const [editingDesc, setEditingDesc] = useState(false);
  const [descDraft, setDescDraft] = useState(doc.description);
  const descRef = useRef<HTMLTextAreaElement>(null);
  const color = TYPE_COLORS[doc.type] ?? "#5a6a78";

  const saveDesc = () => {
    onUpdateDescription(descDraft);
    setEditingDesc(false);
  };

  return (
    <tr className="border-b border-border group hover:bg-muted/30 transition-colors">
      {/* Name */}
      <td className="py-4 px-4">
        <div className="flex items-start gap-4">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
            style={{ background: `${color}15`, color }}
          >
            {TYPE_ICONS[doc.type] ?? <File size={14} />}
          </div>
          <div className="min-w-0 flex-1">
            <button
              className="text-sm font-medium text-foreground leading-snug hover:underline truncate max-w-xs text-left block"
              onClick={() => window.open(`file://${doc.name}`, "_blank")}
              title={`Open ${doc.name}`}
            >
              {doc.name}
            </button>

            {editingDesc ? (
              <div className="mt-1.5 flex flex-col gap-1.5">
                <textarea
                  ref={descRef}
                  rows={2}
                  value={descDraft}
                  onChange={(e) => setDescDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); saveDesc(); } if (e.key === "Escape") { setDescDraft(doc.description); setEditingDesc(false); } }}
                  className="w-full max-w-xs px-2 py-1.5 text-xs rounded-lg border border-border bg-input-background outline-none focus:ring-1 focus:ring-ring/40 resize-none"
                  style={{ fontFamily: "var(--font-sans)" }}
                  autoFocus
                />
                <div className="flex items-center gap-1">
                  <button onClick={saveDesc} className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium text-white" style={{ background: "var(--primary)" }}>
                    <Check size={10} /> Save
                  </button>
                  <button onClick={() => { setDescDraft(doc.description); setEditingDesc(false); }} className="px-2 py-0.5 rounded text-xs text-muted-foreground border border-border hover:bg-muted transition-colors">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-1 mt-0.5 group/desc">
                {doc.description
                  ? <span className="text-xs text-muted-foreground leading-relaxed">{doc.description}</span>
                  : <span className="text-xs text-muted-foreground/50 italic">No description</span>
                }
                <button
                  onClick={() => { setDescDraft(doc.description); setEditingDesc(true); }}
                  className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors opacity-0 group-hover:opacity-100 group-hover/desc:opacity-100 flex-shrink-0 mt-0.5"
                  title="Edit description"
                >
                  <Pencil size={10} />
                </button>
              </div>
            )}

            {doc.fromFolder && (
              <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                <Folder size={10} /> {doc.fromFolder}
              </div>
            )}
          </div>
        </div>
      </td>

      {/* Type */}
      <td className="py-4 px-4">
        <span
          className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium"
          style={{ background: `${color}12`, color }}
        >
          {TYPE_ICONS[doc.type]} {TYPE_LABELS[doc.type] ?? doc.type.toUpperCase()}
        </span>
      </td>

      {/* Size */}
      <td className="py-4 px-4 text-xs text-muted-foreground whitespace-nowrap">{doc.size}</td>

      {/* Tags */}
      <td className="py-4 px-4">
        <div className="relative flex flex-wrap gap-1 items-center">
          {doc.tagIds.map((id) => {
            const tag = tags.find((t) => t.id === id);
            if (!tag) return null;
            const tt = tagTypes.find((t) => t.id === tag.typeId);
            return <TagPill key={id} tag={tag} tagType={tt} size="sm" />;
          })}
          {doc.tagIds.length === 0 && <span className="text-xs text-muted-foreground">—</span>}
          <button
            onClick={() => setEditingTags(true)}
            className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0"
            title="Edit tags"
          >
            <Pencil size={11} />
          </button>
          {editingTags && (
            <TagEditor
              doc={doc}
              tags={tags}
              tagTypes={tagTypes}
              onSave={onUpdateTags}
              onClose={() => setEditingTags(false)}
            />
          )}
        </div>
      </td>

      {/* Uploaded */}
      <td className="py-4 px-4">
        <div className="text-xs text-foreground whitespace-nowrap">{doc.uploadedAt}</div>
        <div className="text-xs text-muted-foreground mt-0.5 whitespace-nowrap">
          {doc.uploadedAtTime ?? ""}
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">{doc.uploadedBy}</div>
      </td>

      {/* Actions */}
      <td className="py-4 px-4">
        <div className="relative">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors opacity-0 group-hover:opacity-100"
          >
            <MoreHorizontal size={14} />
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
              <div className="absolute right-0 top-8 z-20 w-40 rounded-xl border border-border shadow-lg py-1" style={{ background: "var(--card)" }}>
                <button
                  onClick={() => { onDelete(); setMenuOpen(false); }}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-muted transition-colors"
                  style={{ color: "var(--destructive)" }}
                >
                  <Trash2 size={12} /> Delete
                </button>
              </div>
            </>
          )}
        </div>
      </td>
    </tr>
  );
}

// AI vector storage: each doc contributes a base amount + bonus per chat usage.
// Total quota is a fixed 500 MB of extracted embedding / chunk data.
const AI_STORAGE_QUOTA_MB = 500;
function calcAiStorageMB(docs: Document[]): number {
  return docs.reduce((sum, d) => {
    const baseMB = 0.8 + (d.sizeBytes / (1024 * 1024)) * 0.12;
    const chatBonus = d.usedInChats * 0.05;
    return sum + baseMB + chatBonus;
  }, 0);
}

function formatMB(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${mb.toFixed(1)} MB`;
}

export function DocumentLibrary({ documents, tags, tagTypes, onDocumentsChange, onTagsChange, onTagTypesChange }: DocumentLibraryProps) {
  const [search, setSearch] = useState("");
  const [filterTagIds, setFilterTagIds] = useState<string[]>([]);
  const [showUpload, setShowUpload] = useState(false);
  const [showTagManager, setShowTagManager] = useState(false);

  const toggleFilterTag = (id: string) =>
    setFilterTagIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const aiUsedMB = calcAiStorageMB(documents);
  const aiPct = Math.min((aiUsedMB / AI_STORAGE_QUOTA_MB) * 100, 100);
  const aiNearFull = aiPct >= 80;
  const aiBarColor = aiPct >= 90 ? "var(--destructive)" : aiPct >= 80 ? "#D97706" : "var(--primary)";

  // Always sort newest first
  const sorted = [...documents].sort((a, b) => b.uploadedAtMs - a.uploadedAtMs);

  const filtered = sorted.filter((d) => {
    const q = search.toLowerCase();
    const matchesSearch =
      d.name.toLowerCase().includes(q) ||
      d.description.toLowerCase().includes(q) ||
      d.uploadedBy.toLowerCase().includes(q);
    const matchesTags = filterTagIds.length === 0 || filterTagIds.every((id) => d.tagIds.includes(id));
    return matchesSearch && matchesTags;
  });

  const usedTagIds = Array.from(new Set(documents.flatMap((d) => d.tagIds)));

  const handleUploadComplete = (newDocs: Document[]) => {
    // Prepend new docs (they will be sorted to top automatically)
    onDocumentsChange([...newDocs, ...documents]);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-8 pt-6 pb-4 border-b border-border flex-shrink-0">
        <div className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-foreground">Document Library</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {documents.length} document{documents.length !== 1 ? "s" : ""} · Sorted by upload date, most recent first
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={() => setShowTagManager(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border border-border hover:bg-muted transition-colors"
              style={{ color: "var(--foreground)" }}
            >
              <Settings2 size={14} /> Manage Tags
            </button>
            <button
              onClick={() => setShowUpload(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white transition-opacity hover:opacity-80"
              style={{ background: "var(--primary)" }}
            >
              <Upload size={14} /> Upload
            </button>
          </div>
        </div>

        {/* AI Vector Storage bar */}
        <div className="mt-4 p-4 rounded-xl border border-border" style={{ background: "var(--muted)" }}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Database size={13} className="text-muted-foreground" />
              <span className="text-xs font-medium text-foreground">AI Knowledge Storage</span>
              {aiNearFull && (
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full" style={{ background: aiPct >= 90 ? "rgba(231,35,0,0.1)" : "rgba(217,119,6,0.1)", color: aiBarColor }}>
                  {aiPct >= 90 ? "Almost full" : "Nearing limit"}
                </span>
              )}
            </div>
            <span className="text-xs text-muted-foreground tabular-nums">
              {formatMB(aiUsedMB)} <span className="text-muted-foreground/60">/ {formatMB(AI_STORAGE_QUOTA_MB)}</span>
            </span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${aiPct}%`, background: aiBarColor }}
            />
          </div>
          <p className="text-[10px] text-muted-foreground mt-1.5">
            Extracted embeddings and chunk data indexed by the AI assistant · {aiPct.toFixed(1)}% used
          </p>
        </div>
      </div>

      {/* Filter bar */}
      <div className="px-8 py-4 border-b border-border flex items-center gap-4 flex-wrap flex-shrink-0">
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search documents…"
            className="pl-8 pr-4 py-2 rounded-lg text-sm border border-border bg-card outline-none focus:ring-1 focus:ring-ring/40 w-56"
            style={{ fontFamily: "var(--font-sans)" }}
          />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {usedTagIds.slice(0, 10).map((id) => {
            const tag = tags.find((t) => t.id === id);
            if (!tag) return null;
            return (
              <TagPill
                key={id}
                tag={tag}
                selected={filterTagIds.includes(id)}
                onClick={() => toggleFilterTag(id)}
                size="sm"
              />
            );
          })}
          {filterTagIds.length > 0 && (
            <button onClick={() => setFilterTagIds([])} className="text-xs text-muted-foreground underline hover:text-foreground">
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto px-8 py-4" style={{ scrollbarWidth: "thin" }}>
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 gap-2">
            <File size={24} className="text-muted-foreground opacity-40" />
            <p className="text-sm text-muted-foreground">No documents match your filters</p>
            {filterTagIds.length > 0 && (
              <button onClick={() => setFilterTagIds([])} className="text-xs underline text-muted-foreground">Clear filters</button>
            )}
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                {["Document", "Type", "Size", "Tags", "Uploaded", ""].map((h) => (
                  <th
                    key={h}
                    className="text-left py-2 px-4 text-xs font-medium text-muted-foreground"
                    style={{ letterSpacing: "0.05em" }}
                  >
                    {h.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((doc) => (
                <DocRow
                  key={doc.id}
                  doc={doc}
                  tags={tags}
                  tagTypes={tagTypes}
                  onDelete={() => onDocumentsChange(documents.filter((d) => d.id !== doc.id))}
                  onUpdateTags={(tagIds) => onDocumentsChange(documents.map((d) => d.id === doc.id ? { ...d, tagIds } : d))}
                  onUpdateDescription={(description) => onDocumentsChange(documents.map((d) => d.id === doc.id ? { ...d, description } : d))}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          existingDocuments={documents}
          tags={tags}
          tagTypes={tagTypes}
          onUploadComplete={handleUploadComplete}
          onAddTag={(tag) => onTagsChange([...tags, tag])}
        />
      )}
      {showTagManager && (
        <TagManagerModal
          onClose={() => setShowTagManager(false)}
          tagTypes={tagTypes}
          tags={tags}
          onAddTagType={(tt) => onTagTypesChange([...tagTypes, tt])}
          onUpdateTagType={(tt) => onTagTypesChange(tagTypes.map((t) => (t.id === tt.id ? tt : t)))}
          onDeleteTagType={(id) => { onTagTypesChange(tagTypes.filter((t) => t.id !== id)); onTagsChange(tags.filter((t) => t.typeId !== id)); }}
          onAddTag={(tag) => onTagsChange([...tags, tag])}
          onDeleteTag={(id) => onTagsChange(tags.filter((t) => t.id !== id))}
        />
      )}
    </div>
  );
}
