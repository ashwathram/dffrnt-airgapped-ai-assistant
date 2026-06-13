import { useState, useRef } from "react";
import {
  X, Upload, FileText, FileSpreadsheet, File, Plus, AlertTriangle,
  CheckCircle, XCircle, RefreshCw, FilePlus, ChevronDown, ChevronUp,
  Tag as TagIcon, Folder, AlertCircle,
} from "lucide-react";
import { Tag, TagType, Document } from "../types";
import { TagPill } from "./TagPill";

type DuplicateKind = "name" | "content";
type UploadStage = "select" | "checking" | "duplicate" | "uploading" | "result";
type ResultKind = "success" | "cancelled" | "replaced" | "copy" | "error";

const SUPPORTED_TYPES = ["pdf", "xlsx", "docx", "txt", "xls", "doc"];
const MAX_SIZE_MB = 50;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

interface FileEntry {
  file: File;
  description: string;
  selectedTagIds: string[];
  duplicateKind?: DuplicateKind;
  duplicateDocName?: string;
  action?: "cancel" | "replace" | "copy";
  result?: ResultKind;
  validationError?: string;
  fromFolder?: string;
}

interface FolderGroup {
  folderName: string;
  description: string;
  selectedTagIds: string[];
  indices: number[];  // indices into entries array
  expanded: boolean;
}

interface UploadModalProps {
  onClose: () => void;
  existingDocuments: Document[];
  tags: Tag[];
  tagTypes: TagType[];
  onUploadComplete: (docs: Document[]) => void;
  onAddTag: (tag: Tag) => void;
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  pdf: <FileText size={16} />,
  xlsx: <FileSpreadsheet size={16} />,
  xls: <FileSpreadsheet size={16} />,
  docx: <File size={16} />,
  doc: <File size={16} />,
  txt: <File size={16} />,
};
const TYPE_COLORS: Record<string, string> = {
  pdf: "#E72300",
  xlsx: "#0a7c4a",
  xls: "#0a7c4a",
  docx: "#0369a1",
  doc: "#0369a1",
  txt: "#5a6a78",
};

function getExt(name: string): string {
  return name.split(".").pop()?.toLowerCase() ?? "";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function validateFile(file: File): string | undefined {
  const ext = getExt(file.name);
  if (!SUPPORTED_TYPES.includes(ext)) {
    return `Unsupported file type (.${ext || "unknown"}). Accepted: PDF, DOCX, XLSX, TXT`;
  }
  if (file.size === 0) {
    return "File is empty";
  }
  if (file.size > MAX_SIZE_BYTES) {
    return `File exceeds ${MAX_SIZE_MB} MB size limit (${formatSize(file.size)})`;
  }
  return undefined;
}

// ─── Tag Selector ────────────────────────────────────────────────────────────

function TagSelector({
  tags, tagTypes, selectedIds, onToggle, onAddTag,
}: {
  tags: Tag[];
  tagTypes: TagType[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  onAddTag: (tag: Tag) => void;
}) {
  const [collapsedTypeIds, setCollapsedTypeIds] = useState<Set<string>>(new Set());
  const [newTagName, setNewTagName] = useState("");
  const [newTagTypeId, setNewTagTypeId] = useState(tagTypes[0]?.id ?? "");
  const [showCreate, setShowCreate] = useState(false);

  const handleCreate = () => {
    const name = newTagName.trim();
    if (!name || !newTagTypeId) return;
    const tag: Tag = { id: `t-${Date.now()}`, name, typeId: newTagTypeId };
    onAddTag(tag);
    onToggle(tag.id);
    setNewTagName("");
    setShowCreate(false);
  };

  const toggleType = (id: string) =>
    setCollapsedTypeIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <div className="flex flex-col gap-2">
      {selectedIds.length > 0 && (
        <div className="flex flex-wrap gap-2 p-2 rounded-lg bg-muted/50">
          {selectedIds.map((id) => {
            const tag = tags.find((t) => t.id === id);
            if (!tag) return null;
            const tt = tagTypes.find((t) => t.id === tag.typeId);
            return <TagPill key={id} tag={tag} tagType={tt} onRemove={() => onToggle(id)} size="sm" />;
          })}
        </div>
      )}

      <div className="border border-border rounded-lg overflow-hidden divide-y divide-border">
        {tagTypes.map((tt) => {
          const typeTags = tags.filter((t) => t.typeId === tt.id);
          const isOpen = !collapsedTypeIds.has(tt.id);
          const selectedCount = typeTags.filter((t) => selectedIds.includes(t.id)).length;
          return (
            <div key={tt.id}>
              <button
                type="button"
                onClick={() => toggleType(tt.id)}
                className="w-full flex items-center gap-2 px-4 py-2 hover:bg-muted/40 transition-colors text-sm"
              >
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: tt.color }} />
                <span className="flex-1 text-left font-medium text-foreground">{tt.name}</span>
                {selectedCount > 0 && (
                  <span className="text-xs px-1.5 py-0.5 rounded-full text-white font-medium" style={{ background: tt.color }}>
                    {selectedCount}
                  </span>
                )}
                {isOpen ? <ChevronUp size={12} className="text-muted-foreground" /> : <ChevronDown size={12} className="text-muted-foreground" />}
              </button>
              {isOpen && (
                <div className="px-4 pb-4 pt-2 flex flex-wrap gap-2">
                  {typeTags.map((tag) => (
                    <button
                      key={tag.id}
                      type="button"
                      onClick={() => onToggle(tag.id)}
                      className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium transition-all"
                      style={{
                        background: selectedIds.includes(tag.id) ? tt.color : `${tt.color}15`,
                        color: selectedIds.includes(tag.id) ? "#fff" : tt.color,
                        border: `1px solid ${tt.color}40`,
                      }}
                    >
                      {tag.name}
                    </button>
                  ))}
                  {typeTags.length === 0 && (
                    <span className="text-xs text-muted-foreground">No tags in this type yet</span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {showCreate ? (
        <div className="flex gap-2 p-2 rounded-lg border border-dashed border-border">
          <input
            autoFocus
            value={newTagName}
            onChange={(e) => setNewTagName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            placeholder="Tag name…"
            className="flex-1 px-2 py-1 text-xs rounded border border-border bg-input-background outline-none"
          />
          <select
            value={newTagTypeId}
            onChange={(e) => setNewTagTypeId(e.target.value)}
            className="px-2 py-1 text-xs rounded border border-border bg-input-background outline-none"
          >
            {tagTypes.map((tt) => <option key={tt.id} value={tt.id}>{tt.name}</option>)}
          </select>
          <button type="button" onClick={handleCreate} className="px-2 py-1 rounded text-xs font-medium text-white" style={{ background: "var(--primary)" }}>Add</button>
          <button type="button" onClick={() => setShowCreate(false)} className="px-2 py-1 rounded text-xs text-muted-foreground border border-border">Cancel</button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors self-start"
        >
          <Plus size={12} /> Create custom tag
        </button>
      )}
    </div>
  );
}

// ─── Result helpers ───────────────────────────────────────────────────────────

function ResultIcon({ kind }: { kind: ResultKind }) {
  if (kind === "success" || kind === "replaced" || kind === "copy")
    return <CheckCircle size={16} className="text-green-600 flex-shrink-0" />;
  if (kind === "cancelled")
    return <XCircle size={16} className="text-muted-foreground flex-shrink-0" />;
  return <AlertCircle size={16} className="flex-shrink-0" style={{ color: "var(--destructive)" }} />;
}

function resultLabel(entry: FileEntry): string {
  if (entry.validationError && entry.result === "error") return `Failed: ${entry.validationError}`;
  switch (entry.result) {
    case "success": return `Successfully uploaded "${entry.file.name}"`;
    case "replaced": return `Replaced existing version of "${entry.duplicateDocName}"`;
    case "copy": return `Uploaded copy of "${entry.duplicateDocName}"`;
    case "cancelled": return `Upload cancelled — "${entry.file.name}"`;
    case "error": return `Upload failed — "${entry.file.name}". Please try again`;
    default: return "";
  }
}

// ─── Main component ───────────────────────────────────────────────────────────

export function UploadModal({
  onClose, existingDocuments, tags, tagTypes, onUploadComplete, onAddTag,
}: UploadModalProps) {
  const [stage, setStage] = useState<UploadStage>("select");
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [folderGroups, setFolderGroups] = useState<FolderGroup[]>([]);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [duplicateIdx, setDuplicateIdx] = useState<number>(0);
  const [localTags, setLocalTags] = useState<Tag[]>(tags);
  const [progress, setProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  // ── Add files (flat) ────────────────────────────────────────────────────────
  const addFiles = (files: File[], fromFolder?: string, folderTagIds?: string[], folderDescription?: string) => {
    const newEntries: FileEntry[] = files.map((f) => ({
      file: f,
      description: folderDescription ?? "",
      selectedTagIds: folderTagIds ? [...folderTagIds] : [],
      validationError: validateFile(f),
      fromFolder,
    }));
    setEntries((prev) => {
      const next = [...prev, ...newEntries];
      if (expandedIdx === null) setExpandedIdx(prev.length);
      return next;
    });
  };

  // ── Add a folder ────────────────────────────────────────────────────────────
  const addFolder = (files: File[]) => {
    if (files.length === 0) return;
    // Extract folder name from webkitRelativePath
    const folderName = files[0].webkitRelativePath.split("/")[0] || "Folder";
    const startIdx = entries.length;
    const group: FolderGroup = {
      folderName,
      description: "",
      selectedTagIds: [],
      indices: files.map((_, i) => startIdx + i),
      expanded: true,
    };
    const newEntries: FileEntry[] = files.map((f) => ({
      file: f,
      description: "",
      selectedTagIds: [],
      validationError: validateFile(f),
      fromFolder: folderName,
    }));
    setEntries((prev) => [...prev, ...newEntries]);
    setFolderGroups((prev) => [...prev, group]);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const items = Array.from(e.dataTransfer.items);
    const files = Array.from(e.dataTransfer.files);
    // Simple: treat dropped files as flat
    addFiles(files);
  };

  const removeEntry = (idx: number) => {
    setEntries((prev) => prev.filter((_, i) => i !== idx));
    setFolderGroups((prev) =>
      prev
        .map((g) => ({ ...g, indices: g.indices.filter((i) => i !== idx).map((i) => (i > idx ? i - 1 : i)) }))
        .filter((g) => g.indices.length > 0)
    );
  };

  const updateFolderGroup = (gIdx: number, patch: Partial<FolderGroup>) => {
    setFolderGroups((prev) => prev.map((g, i) => (i === gIdx ? { ...g, ...patch } : g)));
    // Propagate tags and description to all files in this group
    const group = folderGroups[gIdx];
    if (patch.selectedTagIds !== undefined || patch.description !== undefined) {
      const tagIds = patch.selectedTagIds ?? group.selectedTagIds;
      const desc = patch.description ?? group.description;
      setEntries((prev) =>
        prev.map((e, i) =>
          group.indices.includes(i) ? { ...e, selectedTagIds: [...tagIds], description: desc } : e
        )
      );
    }
  };

  const toggleTag = (idx: number, tagId: string) => {
    setEntries((prev) =>
      prev.map((e, i) => {
        if (i !== idx) return e;
        const has = e.selectedTagIds.includes(tagId);
        return { ...e, selectedTagIds: has ? e.selectedTagIds.filter((id) => id !== tagId) : [...e.selectedTagIds, tagId] };
      })
    );
  };

  const handleAddTag = (tag: Tag) => {
    setLocalTags((prev) => [...prev, tag]);
    onAddTag(tag);
  };

  // ── Validation summary ──────────────────────────────────────────────────────
  const invalidEntries = entries.filter((e) => e.validationError);
  const validEntries = entries.filter((e) => !e.validationError);

  // ── Upload flow ─────────────────────────────────────────────────────────────
  const startUpload = () => {
    if (validEntries.length === 0) return;
    setStage("checking");
    setTimeout(() => {
      const checked = entries.map((e) => {
        if (e.validationError) return e;
        const nameDup = existingDocuments.find((d) => d.name.toLowerCase() === e.file.name.toLowerCase());
        const contentDup = !nameDup && existingDocuments.find((d) => e.file.size > 3_000_000 && d.size.includes("4"));
        if (nameDup) return { ...e, duplicateKind: "name" as DuplicateKind, duplicateDocName: nameDup.name };
        if (contentDup) return { ...e, duplicateKind: "content" as DuplicateKind, duplicateDocName: contentDup.name };
        return e;
      });
      setEntries(checked);
      const firstDupIdx = checked.findIndex((e) => !e.validationError && e.duplicateKind);
      if (firstDupIdx >= 0) {
        setDuplicateIdx(firstDupIdx);
        setStage("duplicate");
      } else {
        doUpload(checked);
      }
    }, 800);
  };

  const resolveDuplicate = (action: "cancel" | "replace" | "copy") => {
    const updated = entries.map((e, i) => (i === duplicateIdx ? { ...e, action } : e));
    setEntries(updated);
    const next = updated.findIndex((e, i) => i > duplicateIdx && e.duplicateKind && !e.action);
    if (next >= 0) setDuplicateIdx(next);
    else doUpload(updated);
  };

  const doUpload = (resolved: FileEntry[]) => {
    setStage("uploading");
    setProgress(0);
    const interval = setInterval(() => {
      setProgress((p) => (p >= 100 ? 100 : p + Math.random() * 16));
    }, 100);
    setTimeout(() => {
      clearInterval(interval);
      setProgress(100);
      const now = Date.now();
      const results: FileEntry[] = resolved.map((e) => {
        if (e.validationError) return { ...e, result: "error" as ResultKind };
        if (e.action === "cancel") return { ...e, result: "cancelled" as ResultKind };
        if (e.action === "replace") return { ...e, result: "replaced" as ResultKind };
        if (e.action === "copy") return { ...e, result: "copy" as ResultKind };
        return { ...e, result: (Math.random() < 0.06 ? "error" : "success") as ResultKind };
      });
      setEntries(results);
      setStage("result");

      const newDocs: Document[] = results
        .filter((e) => e.result === "success" || e.result === "copy")
        .map((e) => {
          const ext = getExt(e.file.name);
          const uploadDate = new Date();
          return {
            id: `doc-${now}-${Math.random().toString(36).slice(2)}`,
            name: e.result === "copy" ? `${e.file.name} (copy)` : e.file.name,
            type: (["pdf","xlsx","docx","txt"].includes(ext) ? ext : "txt") as Document["type"],
            size: formatSize(e.file.size),
            sizeBytes: e.file.size,
            uploadedAt: uploadDate.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }),
            uploadedAtMs: now,
            uploadedBy: "System",
            tagIds: e.selectedTagIds,
            description: e.description,
            usedInChats: 0,
            fromFolder: e.fromFolder,
          };
        });
      onUploadComplete(newDocs);
    }, 1600);
  };

  // ── Grouped view: standalone files vs folder groups ─────────────────────────
  const standaloneIndices = entries
    .map((e, i) => (e.fromFolder ? null : i))
    .filter((i): i is number => i !== null);

  // ── Render: checking / uploading ────────────────────────────────────────────
  if (stage === "checking" || stage === "uploading") {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-8" style={{ background: "rgba(9,26,41,0.5)" }}>
        <div className="w-full max-w-sm rounded-2xl shadow-2xl flex flex-col items-center gap-6 p-8" style={{ background: "var(--card)" }}>
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center" style={{ background: "var(--primary)" }}>
            {stage === "checking" ? <TagIcon size={24} className="text-white animate-pulse" /> : <Upload size={24} className="text-white animate-pulse" />}
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-foreground mb-1">
              {stage === "checking" ? "Checking for duplicates…" : "Uploading documents…"}
            </p>
            <p className="text-xs text-muted-foreground">
              {stage === "checking" ? "Comparing filenames and content signatures" : `Processing ${validEntries.length} file${validEntries.length !== 1 ? "s" : ""}`}
            </p>
          </div>
          {stage === "uploading" && (
            <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
              <div className="h-full rounded-full transition-all duration-150" style={{ width: `${Math.min(progress, 100)}%`, background: "var(--primary)" }} />
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Render: duplicate ───────────────────────────────────────────────────────
  if (stage === "duplicate") {
    const entry = entries[duplicateIdx];
    const remaining = entries.filter((e, i) => i > duplicateIdx && e.duplicateKind && !e.action).length;
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-8" style={{ background: "rgba(9,26,41,0.5)" }}>
        <div className="w-full max-w-md rounded-2xl shadow-2xl overflow-hidden" style={{ background: "var(--card)" }}>
          <div className="px-8 pt-8 pb-4">
            <div className="flex items-center gap-4 mb-6">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: "#FEF3C7" }}>
                <AlertTriangle size={18} style={{ color: "#D97706" }} />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">Duplicate detected</p>
                {remaining > 0 && <p className="text-xs text-muted-foreground">{remaining + 1} duplicates remaining</p>}
              </div>
            </div>
            <div className="p-4 rounded-xl mb-4" style={{ background: "var(--muted)" }}>
              <p className="text-xs text-muted-foreground mb-1">Uploading</p>
              <p className="text-sm font-medium text-foreground">{entry.file.name}</p>
              <div className="mt-2 pt-2 border-t border-border">
                <p className="text-xs text-muted-foreground mb-1">
                  {entry.duplicateKind === "name"
                    ? "A document with the same name already exists:"
                    : "A document with similar content already exists:"}
                </p>
                <p className="text-sm text-foreground">{entry.duplicateDocName}</p>
              </div>
            </div>
          </div>
          <div className="flex flex-col gap-2 px-8 pb-8">
            <button onClick={() => resolveDuplicate("replace")} className="w-full flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-medium text-white" style={{ background: "var(--primary)" }}>
              <RefreshCw size={14} /> Replace current version
            </button>
            <button onClick={() => resolveDuplicate("copy")} className="w-full flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-medium border border-border hover:bg-muted transition-colors" style={{ color: "var(--foreground)" }}>
              <FilePlus size={14} /> Upload anyway (append copy)
            </button>
            <button onClick={() => resolveDuplicate("cancel")} className="w-full flex items-center gap-2 px-4 py-3 rounded-xl text-sm text-muted-foreground hover:text-foreground transition-colors">
              <X size={14} /> Cancel this upload
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Render: result ──────────────────────────────────────────────────────────
  if (stage === "result") {
    const successCount = entries.filter((e) => ["success", "replaced", "copy"].includes(e.result!)).length;
    const errorCount = entries.filter((e) => e.result === "error").length;
    const cancelCount = entries.filter((e) => e.result === "cancelled").length;
    const allCancelled = cancelCount === entries.length;
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-8" style={{ background: "rgba(9,26,41,0.5)" }}>
        <div className="w-full max-w-md rounded-2xl shadow-2xl overflow-hidden" style={{ background: "var(--card)" }}>
          <div className="px-8 pt-8 pb-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: allCancelled ? "var(--muted)" : errorCount === 0 ? "#d1fae5" : "#FEE2E2" }}>
              {allCancelled ? <XCircle size={18} className="text-muted-foreground" /> : errorCount === 0 ? <CheckCircle size={18} className="text-green-600" /> : <AlertTriangle size={18} style={{ color: "var(--destructive)" }} />}
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">
                {allCancelled ? "Upload cancelled" : errorCount === 0 ? "Upload complete" : "Upload finished with errors"}
              </p>
              <p className="text-xs text-muted-foreground">
                {[
                  successCount > 0 && `${successCount} successful`,
                  cancelCount > 0 && `${cancelCount} cancelled`,
                  errorCount > 0 && `${errorCount} failed`,
                ].filter(Boolean).join(" · ")}
              </p>
            </div>
          </div>

          <div className="px-8 pb-2">
            <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium mb-2" style={{ letterSpacing: "0.06em" }}>Ingestion summary</p>
          </div>

          <div className="px-8 pb-4 flex flex-col gap-2 max-h-64 overflow-y-auto" style={{ scrollbarWidth: "thin" }}>
            {entries.map((e, i) => (
              <div key={i} className="flex items-start gap-2 py-2 border-b border-border last:border-0">
                <ResultIcon kind={e.result!} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-foreground leading-snug">{resultLabel(e)}</p>
                  {e.fromFolder && (
                    <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                      <Folder size={10} /> {e.fromFolder}
                    </p>
                  )}
                  {e.selectedTagIds.length > 0 && !["cancelled","error"].includes(e.result!) && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {e.selectedTagIds.slice(0, 3).map((id) => {
                        const tag = localTags.find((t) => t.id === id);
                        const tt = tagTypes.find((t) => t.id === tag?.typeId);
                        return tag ? <TagPill key={id} tag={tag} tagType={tt} size="sm" /> : null;
                      })}
                      {e.selectedTagIds.length > 3 && <span className="text-xs text-muted-foreground">+{e.selectedTagIds.length - 3}</span>}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="px-8 pb-8 border-t border-border pt-4">
            <button onClick={onClose} className="w-full py-3 rounded-xl text-sm font-medium text-white" style={{ background: "var(--primary)" }}>Done</button>
          </div>
        </div>
      </div>
    );
  }

  // ── Render: select ──────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-8" style={{ background: "rgba(9,26,41,0.5)" }}>
      <div className="w-full max-w-2xl rounded-2xl shadow-2xl flex flex-col overflow-hidden" style={{ background: "var(--card)", maxHeight: "88vh" }}>

        {/* Header */}
        <div className="flex items-center justify-between px-8 py-6 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <Upload size={16} style={{ color: "var(--accent)" }} />
            <h2 className="text-base text-foreground">Upload Documents</h2>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: "thin" }}>
          {/* Drop zone */}
          <div className="px-8 pt-6">
            <div
              className="border-2 border-dashed rounded-xl py-8 flex flex-col items-center gap-2 text-sm text-muted-foreground transition-colors cursor-pointer"
              style={{
                borderColor: dragOver ? "var(--accent)" : "var(--border)",
                background: dragOver ? "rgba(93,39,184,0.04)" : "transparent",
              }}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
            >
              <div className="w-12 h-12 rounded-xl flex items-center justify-center mb-2" style={{ background: "var(--muted)" }}>
                <Upload size={20} className="text-muted-foreground" />
              </div>
              <span className="font-medium text-foreground">Drop files or folders here</span>
              <span className="text-xs">PDF, DOCX, XLSX, TXT · Max {MAX_SIZE_MB} MB per file</span>
              <div className="flex items-center gap-2 mt-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 rounded-lg text-xs font-medium border border-border hover:bg-muted transition-colors"
                  style={{ color: "var(--foreground)" }}
                >
                  Browse files
                </button>
                <button
                  type="button"
                  onClick={() => folderInputRef.current?.click()}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium border border-border hover:bg-muted transition-colors"
                  style={{ color: "var(--foreground)" }}
                >
                  <Folder size={12} /> Browse folder
                </button>
              </div>
              <input ref={fileInputRef} type="file" multiple accept=".pdf,.xlsx,.xls,.docx,.doc,.txt" className="hidden" onChange={(e) => addFiles(Array.from(e.target.files ?? []))} />
              <input ref={folderInputRef} type="file" className="hidden"
                /* @ts-ignore */
                webkitdirectory="true" directory="true"
                onChange={(e) => addFolder(Array.from(e.target.files ?? []))}
              />
            </div>
          </div>

          {/* Validation errors banner */}
          {invalidEntries.length > 0 && (
            <div className="mx-8 mt-4 p-4 rounded-xl flex items-start gap-2" style={{ background: "rgba(231,35,0,0.06)", border: "1px solid rgba(231,35,0,0.18)" }}>
              <AlertCircle size={14} className="flex-shrink-0 mt-0.5" style={{ color: "var(--destructive)" }} />
              <div>
                <p className="text-xs font-medium" style={{ color: "var(--destructive)" }}>
                  {invalidEntries.length} file{invalidEntries.length !== 1 ? "s" : ""} cannot be uploaded
                </p>
                <ul className="mt-1 flex flex-col gap-0.5">
                  {invalidEntries.map((e, i) => (
                    <li key={i} className="text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{e.file.name}</span> — {e.validationError}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Folder groups */}
          {folderGroups.map((group, gIdx) => (
            <div key={gIdx} className="mx-8 mt-4 rounded-xl border border-border overflow-hidden">
              <div
                className="flex items-center gap-2 px-4 py-4 cursor-pointer hover:bg-muted/20 transition-colors"
                style={{ background: "rgba(93,39,184,0.04)" }}
                onClick={() => updateFolderGroup(gIdx, { expanded: !group.expanded })}
              >
                <Folder size={15} style={{ color: "var(--accent)" }} className="flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground">{group.folderName}</p>
                  <p className="text-xs text-muted-foreground">{group.indices.length} files · Tags applied to all files</p>
                </div>
                {group.expanded ? <ChevronUp size={14} className="text-muted-foreground" /> : <ChevronDown size={14} className="text-muted-foreground" />}
              </div>
              {group.expanded && (
                <div className="px-4 pb-4 pt-2 flex flex-col gap-4 border-t border-border">
                  {/* Shared description */}
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-2">Description (applied to all files)</label>
                    <textarea
                      rows={2}
                      value={group.description}
                      onChange={(e) => updateFolderGroup(gIdx, { description: e.target.value })}
                      placeholder="Brief description of this folder's content…"
                      className="w-full px-4 py-2 text-sm rounded-lg border border-border bg-input-background outline-none focus:ring-1 focus:ring-ring/40 resize-none"
                      style={{ fontFamily: "var(--font-sans)" }}
                    />
                  </div>
                  {/* Shared tags */}
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-2">Tags (applied to all files)</label>
                    <TagSelector
                      tags={localTags}
                      tagTypes={tagTypes}
                      selectedIds={group.selectedTagIds}
                      onToggle={(id) => {
                        const has = group.selectedTagIds.includes(id);
                        updateFolderGroup(gIdx, {
                          selectedTagIds: has
                            ? group.selectedTagIds.filter((x) => x !== id)
                            : [...group.selectedTagIds, id],
                        });
                      }}
                      onAddTag={handleAddTag}
                    />
                  </div>
                  {/* File list */}
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-2">Files in folder</label>
                    <div className="flex flex-col gap-1">
                      {group.indices.map((idx) => {
                        const e = entries[idx];
                        if (!e) return null;
                        const ext = getExt(e.file.name);
                        return (
                          <div key={idx} className="flex items-center gap-2 px-4 py-2 rounded-lg" style={{ background: "var(--muted)" }}>
                            <div className="w-6 h-6 rounded flex items-center justify-center flex-shrink-0" style={{ background: `${TYPE_COLORS[ext] ?? "#5a6a78"}15`, color: TYPE_COLORS[ext] ?? "#5a6a78" }}>
                              {TYPE_ICONS[ext] ?? <File size={12} />}
                            </div>
                            <span className="text-xs text-foreground flex-1 min-w-0 truncate">{e.file.name}</span>
                            <span className="text-xs text-muted-foreground flex-shrink-0">{formatSize(e.file.size)}</span>
                            {e.validationError && (
                              <AlertCircle size={12} style={{ color: "var(--destructive)" }} title={e.validationError} />
                            )}
                            <button onClick={() => removeEntry(idx)} className="p-1 rounded hover:bg-muted text-muted-foreground flex-shrink-0"><X size={11} /></button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Standalone file entries */}
          {standaloneIndices.length > 0 && (
            <div className="px-8 pt-4 pb-2 flex flex-col gap-4">
              {standaloneIndices.map((idx) => {
                const entry = entries[idx];
                const ext = getExt(entry.file.name);
                const isExpanded = expandedIdx === idx;
                return (
                  <div key={idx} className="rounded-xl border overflow-hidden" style={{ borderColor: entry.validationError ? "rgba(231,35,0,0.4)" : "var(--border)" }}>
                    <div
                      className="flex items-center gap-2 px-4 py-4 cursor-pointer hover:bg-muted/30 transition-colors"
                      onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                    >
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: `${TYPE_COLORS[ext] ?? "#5a6a78"}15`, color: TYPE_COLORS[ext] ?? "#5a6a78" }}>
                        {TYPE_ICONS[ext] ?? <File size={16} />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{entry.file.name}</p>
                        <p className="text-xs text-muted-foreground">{formatSize(entry.file.size)}</p>
                        {entry.validationError && (
                          <p className="text-xs mt-0.5 flex items-center gap-1" style={{ color: "var(--destructive)" }}>
                            <AlertCircle size={11} /> {entry.validationError}
                          </p>
                        )}
                      </div>
                      {!entry.validationError && entry.selectedTagIds.length > 0 && (
                        <span className="text-xs text-muted-foreground mr-2">{entry.selectedTagIds.length} tag{entry.selectedTagIds.length !== 1 ? "s" : ""}</span>
                      )}
                      <button onClick={(ev) => { ev.stopPropagation(); removeEntry(idx); }} className="p-1 rounded hover:bg-muted text-muted-foreground flex-shrink-0"><X size={13} /></button>
                      {!entry.validationError && (isExpanded ? <ChevronUp size={14} className="text-muted-foreground flex-shrink-0" /> : <ChevronDown size={14} className="text-muted-foreground flex-shrink-0" />)}
                    </div>
                    {isExpanded && !entry.validationError && (
                      <div className="px-4 pb-4 flex flex-col gap-4 border-t border-border pt-4">
                        <div>
                          <label className="text-xs font-medium text-muted-foreground block mb-2">Description <span className="font-normal">(optional)</span></label>
                          <textarea
                            rows={2}
                            value={entry.description}
                            onChange={(e) => setEntries((prev) => prev.map((en, i) => i === idx ? { ...en, description: e.target.value } : en))}
                            placeholder="Brief description of this document's content or purpose…"
                            className="w-full px-4 py-2 text-sm rounded-lg border border-border bg-input-background outline-none focus:ring-1 focus:ring-ring/40 resize-none"
                            style={{ fontFamily: "var(--font-sans)" }}
                          />
                        </div>
                        <div>
                          <label className="text-xs font-medium text-muted-foreground block mb-2">Tags</label>
                          <TagSelector
                            tags={localTags}
                            tagTypes={tagTypes}
                            selectedIds={entry.selectedTagIds}
                            onToggle={(id) => toggleTag(idx, id)}
                            onAddTag={handleAddTag}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {entries.length === 0 && <div className="h-4" />}
        </div>

        {/* Footer */}
        <div className="px-8 py-6 border-t border-border flex items-center justify-between flex-shrink-0">
          <div className="text-xs text-muted-foreground">
            {entries.length > 0 && (
              <>
                {validEntries.length} valid · {invalidEntries.length > 0 && <span style={{ color: "var(--destructive)" }}>{invalidEntries.length} invalid</span>}
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="px-4 py-2 rounded-xl text-sm text-muted-foreground border border-border hover:bg-muted transition-colors">Cancel</button>
            <button
              onClick={startUpload}
              disabled={validEntries.length === 0}
              className="px-6 py-2 rounded-xl text-sm font-medium text-white transition-opacity disabled:opacity-40"
              style={{ background: "var(--primary)" }}
            >
              Upload {validEntries.length > 0 ? `${validEntries.length} file${validEntries.length !== 1 ? "s" : ""}` : ""}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
