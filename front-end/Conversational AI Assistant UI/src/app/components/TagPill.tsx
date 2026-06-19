import { X } from "lucide-react";
import { Tag, TagType } from "../types";

interface TagPillProps {
  tag: Tag;
  tagType?: TagType;
  onRemove?: () => void;
  size?: "sm" | "md";
  onClick?: () => void;
  selected?: boolean;
}

export function TagPill({ tag, tagType, onRemove, size = "md", onClick, selected }: TagPillProps) {
  const color = tagType?.color ?? "#5a6a78";
  const isClickable = !!onClick;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full transition-all ${
        size === "sm" ? "px-2 py-0.5" : "px-2.5 py-1"
      } ${isClickable ? "cursor-pointer" : ""}`}
      style={{
        background: selected ? color : `${color}18`,
        color: selected ? "#ffffff" : color,
        border: `1px solid ${color}30`,
        fontSize: size === "sm" ? "11px" : "12px",
        fontWeight: 500,
      }}
      onClick={onClick}
    >
      {tagType && (
        <span
          className="opacity-60"
          style={{ fontSize: size === "sm" ? "9px" : "10px" }}
        >
          {tagType.name} ·
        </span>
      )}
      {tag.name}
      {onRemove && (
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="hover:opacity-70 transition-opacity ml-0.5"
        >
          <X size={10} />
        </button>
      )}
    </span>
  );
}
