import { useState } from "react";
import { X, Plus, Trash2, Pencil, Check, ChevronDown, ChevronRight, Tag as TagIcon } from "lucide-react";
import { Tag, TagType } from "../types";

interface TagManagerModalProps {
  onClose: () => void;
  tagTypes: TagType[];
  tags: Tag[];
  onAddTagType: (tt: TagType) => void;
  onUpdateTagType: (tt: TagType) => void;
  onDeleteTagType: (id: string) => void;
  onAddTag: (tag: Tag) => void;
  onDeleteTag: (id: string) => void;
}

const PRESET_COLORS = [
  "#5D27B8", "#E72300", "#091A29", "#0a7c4a",
  "#0369a1", "#b45309", "#9d174d", "#4338ca",
];

export function TagManagerModal({
  onClose,
  tagTypes,
  tags,
  onAddTagType,
  onUpdateTagType,
  onDeleteTagType,
  onAddTag,
  onDeleteTag,
}: TagManagerModalProps) {
  const [expandedTypes, setExpandedTypes] = useState<Record<string, boolean>>({});
  const [editingTypeId, setEditingTypeId] = useState<string | null>(null);
  const [editingTypeName, setEditingTypeName] = useState("");
  const [editingTypeColor, setEditingTypeColor] = useState("");
  const [editingTypeDesc, setEditingTypeDesc] = useState("");

  const [newTypeName, setNewTypeName] = useState("");
  const [newTypeColor, setNewTypeColor] = useState(PRESET_COLORS[0]);
  const [newTypeDesc, setNewTypeDesc] = useState("");
  const [showNewTypeForm, setShowNewTypeForm] = useState(false);

  const [newTagInputs, setNewTagInputs] = useState<Record<string, string>>({});

  const toggleExpand = (id: string) =>
    setExpandedTypes((p) => ({ ...p, [id]: !p[id] }));

  const startEdit = (tt: TagType) => {
    setEditingTypeId(tt.id);
    setEditingTypeName(tt.name);
    setEditingTypeColor(tt.color);
    setEditingTypeDesc(tt.description ?? "");
  };

  const saveEdit = () => {
    if (!editingTypeId || !editingTypeName.trim()) return;
    onUpdateTagType({
      id: editingTypeId,
      name: editingTypeName.trim(),
      color: editingTypeColor,
      description: editingTypeDesc.trim() || undefined,
    });
    setEditingTypeId(null);
  };

  const handleAddType = () => {
    if (!newTypeName.trim()) return;
    onAddTagType({
      id: `tt-${Date.now()}`,
      name: newTypeName.trim(),
      color: newTypeColor,
      description: newTypeDesc.trim() || undefined,
    });
    setNewTypeName("");
    setNewTypeDesc("");
    setNewTypeColor(PRESET_COLORS[0]);
    setShowNewTypeForm(false);
  };

  const handleAddTag = (typeId: string) => {
    const name = newTagInputs[typeId]?.trim();
    if (!name) return;
    onAddTag({ id: `t-${Date.now()}`, name, typeId });
    setNewTagInputs((p) => ({ ...p, [typeId]: "" }));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(9,26,41,0.5)", padding: "2rem" }}>
      <div
        className="w-full max-w-2xl rounded-2xl shadow-2xl overflow-hidden"
        style={{
          background: "var(--card)",
          height: "calc(100vh - 4rem)",
          display: "grid",
          gridTemplateRows: "auto 1fr auto",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <TagIcon size={16} style={{ color: "var(--accent)" }} />
            <h2 className="text-base text-foreground">Tag Manager</h2>
          </div>
          <button onClick={onClose} className="p-2 rounded hover:bg-muted text-muted-foreground transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Scroll area — the 1fr grid row gives it an exact height budget */}
        <div style={{ overflowY: "auto", scrollbarWidth: "thin" }}>
        <div className="px-6 py-4 flex flex-col gap-4">
          {tagTypes.map((tt) => {
            const typeTags = tags.filter((t) => t.typeId === tt.id);
            const expanded = expandedTypes[tt.id] ?? false;
            const isEditing = editingTypeId === tt.id;

            return (
              <div
                key={tt.id}
                className="rounded-xl border border-border overflow-hidden"
              >
                {/* Type header */}
                <div
                  className="flex items-center gap-4 px-4 py-4 cursor-pointer hover:bg-muted/40 transition-colors"
                  style={{ background: `${tt.color}08` }}
                  onClick={() => !isEditing && toggleExpand(tt.id)}
                >
                  <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: tt.color }} />
                  {isEditing ? (
                    <div className="flex-1 flex items-start gap-2 flex-wrap" onClick={(e) => e.stopPropagation()}>
                      <input
                        autoFocus
                        value={editingTypeName}
                        onChange={(e) => setEditingTypeName(e.target.value)}
                        className="flex-1 min-w-0 px-2 py-1 text-sm rounded border border-border outline-none bg-card"
                        placeholder="Type name"
                      />
                      <input
                        value={editingTypeDesc}
                        onChange={(e) => setEditingTypeDesc(e.target.value)}
                        className="flex-1 min-w-0 px-2 py-1 text-sm rounded border border-border outline-none bg-card"
                        placeholder="Description (optional)"
                      />
                      <div className="flex gap-1 flex-wrap">
                        {PRESET_COLORS.map((c) => (
                          <button
                            key={c}
                            onClick={() => setEditingTypeColor(c)}
                            className="w-5 h-5 rounded-full transition-transform"
                            style={{
                              background: c,
                              outline: editingTypeColor === c ? `2px solid ${c}` : "none",
                              outlineOffset: "2px",
                              transform: editingTypeColor === c ? "scale(1.15)" : "scale(1)",
                            }}
                          />
                        ))}
                      </div>
                      <button
                        onClick={saveEdit}
                        className="px-3 py-1 rounded-lg text-xs font-medium text-white"
                        style={{ background: "var(--primary)" }}
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setEditingTypeId(null)}
                        className="px-3 py-1 rounded-lg text-xs text-muted-foreground border border-border"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-medium text-foreground">{tt.name}</span>
                        {tt.description && (
                          <span className="text-xs text-muted-foreground ml-2">{tt.description}</span>
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground mr-2">{typeTags.length} tags</span>
                      <button
                        onClick={(e) => { e.stopPropagation(); startEdit(tt); }}
                        className="p-1 rounded hover:bg-muted text-muted-foreground transition-colors"
                      >
                        <Pencil size={12} />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); onDeleteTagType(tt.id); }}
                        className="p-1 rounded hover:bg-muted transition-colors"
                        style={{ color: "var(--destructive)" }}
                      >
                        <Trash2 size={12} />
                      </button>
                      {expanded ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
                    </>
                  )}
                </div>

                {/* Tags */}
                {expanded && !isEditing && (
                  <div className="px-4 pb-4 pt-2 flex flex-col gap-2">
                    <div className="flex flex-wrap gap-2">
                      {typeTags.map((tag) => (
                        <span
                          key={tag.id}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
                          style={{ background: `${tt.color}18`, color: tt.color, border: `1px solid ${tt.color}30` }}
                        >
                          {tag.name}
                          <button
                            onClick={() => onDeleteTag(tag.id)}
                            className="hover:opacity-70 transition-opacity"
                          >
                            <X size={9} />
                          </button>
                        </span>
                      ))}
                      {typeTags.length === 0 && (
                        <span className="text-xs text-muted-foreground">No tags yet</span>
                      )}
                    </div>
                    <div className="flex gap-2 mt-1">
                      <input
                        value={newTagInputs[tt.id] ?? ""}
                        onChange={(e) => setNewTagInputs((p) => ({ ...p, [tt.id]: e.target.value }))}
                        onKeyDown={(e) => e.key === "Enter" && handleAddTag(tt.id)}
                        placeholder={`Add tag to ${tt.name}…`}
                        className="flex-1 px-4 py-2 text-xs rounded-lg border border-border bg-input-background outline-none focus:ring-1 focus:ring-ring/40"
                      />
                      <button
                        onClick={() => handleAddTag(tt.id)}
                        className="px-4 py-2 rounded-lg text-xs font-medium text-white transition-opacity hover:opacity-80"
                        style={{ background: tt.color }}
                      >
                        Add
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {/* Add new type */}
          {showNewTypeForm ? (
            <div className="rounded-xl border-2 border-dashed border-border p-4 flex flex-col gap-4">
              <p className="text-sm font-medium text-foreground">New Tag Type</p>
              <div className="grid grid-cols-2 gap-2">
                <input
                  autoFocus
                  value={newTypeName}
                  onChange={(e) => setNewTypeName(e.target.value)}
                  placeholder="Type name (e.g. Region)"
                  className="px-3 py-2 text-sm rounded-lg border border-border bg-input-background outline-none focus:ring-1 focus:ring-ring/40"
                />
                <input
                  value={newTypeDesc}
                  onChange={(e) => setNewTypeDesc(e.target.value)}
                  placeholder="Description (optional)"
                  className="px-3 py-2 text-sm rounded-lg border border-border bg-input-background outline-none focus:ring-1 focus:ring-ring/40"
                />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Color:</span>
                {PRESET_COLORS.map((c) => (
                  <button
                    key={c}
                    onClick={() => setNewTypeColor(c)}
                    className="w-5 h-5 rounded-full transition-transform"
                    style={{
                      background: c,
                      outline: newTypeColor === c ? `2px solid ${c}` : "none",
                      outlineOffset: "2px",
                      transform: newTypeColor === c ? "scale(1.15)" : "scale(1)",
                    }}
                  />
                ))}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleAddType}
                  disabled={!newTypeName.trim()}
                  className="px-4 py-2 rounded-lg text-sm font-medium text-white transition-opacity disabled:opacity-40"
                  style={{ background: "var(--primary)" }}
                >
                  Create Type
                </button>
                <button
                  onClick={() => setShowNewTypeForm(false)}
                  className="px-4 py-2 rounded-lg text-sm text-muted-foreground border border-border"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowNewTypeForm(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl border-2 border-dashed border-border text-sm text-muted-foreground hover:text-foreground hover:border-foreground/20 transition-colors"
            >
              <Plus size={14} />
              New tag type
            </button>
          )}
        </div>
        </div>{/* end scroll area */}

        <div className="px-6 py-4 border-t border-border">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-sm font-medium text-white transition-opacity hover:opacity-80"
            style={{ background: "var(--primary)" }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
