import { useState, useRef, useEffect } from "react";
import {
  MessageSquare, Plus, Library, ChevronDown, ChevronRight,
  Search, Clock, PanelLeft, MoreHorizontal, Pin, Pencil, Trash2,
} from "lucide-react";
import dffrntLogo from "../../imports/dffrnt_logo.jpeg";

type View = "chat" | "library";

interface SidebarProps {
  activeView: View;
  onViewChange: (view: View) => void;
  activeChatId: string | null;
  onChatSelect: (id: string) => void;
  onNewChat: () => void;
  collapsed: boolean;
  onToggle: () => void;
}

interface Chat {
  id: string;
  title: string;
  timestamp: string;
  group: "Pinned" | "Today" | "Yesterday" | "Last 7 days";
  pinned?: boolean;
}

const INITIAL_CHATS: Chat[] = [
  { id: "1", title: "Q3 Financial Report Analysis", timestamp: "2h ago", group: "Today" },
  { id: "2", title: "Product Roadmap Review", timestamp: "4h ago", group: "Today" },
  { id: "3", title: "Competitor Benchmarking", timestamp: "Yesterday", group: "Yesterday" },
  { id: "4", title: "Customer Feedback Summary", timestamp: "2d ago", group: "Last 7 days" },
  { id: "5", title: "Legal Contract Review", timestamp: "3d ago", group: "Last 7 days" },
  { id: "6", title: "Market Expansion Strategy", timestamp: "5d ago", group: "Last 7 days" },
];

export function Sidebar({
  activeView, onViewChange, activeChatId, onChatSelect, onNewChat, collapsed, onToggle,
}: SidebarProps) {
  const [chats, setChats] = useState<Chat[]>(INITIAL_CHATS);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    Pinned: true,
    Today: true,
    Yesterday: false,
    "Last 7 days": false,
  });
  const [searchQuery, setSearchQuery] = useState("");
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);

  const toggleGroup = (g: string) =>
    setExpandedGroups((p) => ({ ...p, [g]: !p[g] }));

  const handlePin = (id: string) => {
    setChats((prev) =>
      prev.map((c) =>
        c.id === id
          ? { ...c, pinned: !c.pinned, group: c.pinned ? (c.group === "Pinned" ? "Today" : c.group) : "Pinned" }
          : c
      )
    );
    setMenuOpenId(null);
  };

  const handleRename = (id: string) => {
    const chat = chats.find((c) => c.id === id);
    if (!chat) return;
    setRenamingId(id);
    setRenameValue(chat.title);
    setMenuOpenId(null);
    setTimeout(() => renameInputRef.current?.focus(), 50);
  };

  const commitRename = (id: string) => {
    const trimmed = renameValue.trim();
    if (trimmed) setChats((prev) => prev.map((c) => (c.id === id ? { ...c, title: trimmed } : c)));
    setRenamingId(null);
  };

  const handleDelete = (id: string) => {
    setChats((prev) => prev.filter((c) => c.id !== id));
    setMenuOpenId(null);
  };

  const filtered = chats.filter((c) =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const groups = ["Pinned", "Today", "Yesterday", "Last 7 days"] as const;

  return (
    <aside
      className="flex flex-col h-full transition-all duration-200 flex-shrink-0"
      style={{
        width: collapsed ? "56px" : "256px",
        minWidth: collapsed ? "56px" : "256px",
        background: "var(--sidebar)",
        borderRight: "1px solid var(--sidebar-border)",
      }}
    >
      {/* Brand */}
      <div
        className="flex items-center h-14 px-2 flex-shrink-0"
        style={{ borderBottom: "1px solid var(--sidebar-border)" }}
      >
        {!collapsed ? (
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <img src={dffrntLogo} alt="DFFRNT" className="w-7 h-7 rounded-md flex-shrink-0 object-cover" />
            <span className="text-sm font-medium truncate" style={{ color: "var(--sidebar-foreground)" }}>
              DFFRNT AI Assistant
            </span>
            <button
              onClick={onToggle}
              className="ml-auto p-1 rounded transition-colors flex-shrink-0"
              style={{ color: "rgba(255,255,255,0.4)" }}
            >
              <PanelLeft size={14} />
            </button>
          </div>
        ) : (
          <div className="w-full flex items-center justify-center">
            <img
              src={dffrntLogo}
              alt="DFFRNT"
              className="w-7 h-7 rounded-md object-cover cursor-pointer"
              onClick={onToggle}
              title="Expand sidebar"
            />
          </div>
        )}
      </div>

      {/* Nav actions */}
      <div className={`${collapsed ? "px-2" : "px-4"} pt-6 pb-2 flex flex-col gap-2 flex-shrink-0`}>
        <button
          onClick={onNewChat}
          title="New chat"
          className={`flex items-center py-2 rounded-lg text-sm font-medium transition-colors w-full ${collapsed ? "justify-center px-0" : "gap-2 px-4"}`}
          style={{
            background: "var(--sidebar-accent)",
            color: "var(--sidebar-foreground)",
          }}
        >
          <Plus size={15} className="flex-shrink-0" />
          {!collapsed && <span>New chat</span>}
        </button>

        <button
          onClick={() => onViewChange("library")}
          title="Document library"
          className={`flex items-center py-2 rounded-lg text-sm transition-colors w-full ${collapsed ? "justify-center px-0" : "gap-2 px-4"}`}
          style={{
            background: activeView === "library" ? "var(--sidebar-accent)" : "transparent",
            color: activeView === "library"
              ? "var(--sidebar-foreground)"
              : "rgba(255,255,255,0.5)",
            fontWeight: activeView === "library" ? 500 : 400,
          }}
        >
          <Library size={15} className="flex-shrink-0" />
          {!collapsed && <span>Document Library</span>}
        </button>
      </div>

      {/* Recent label */}
      {!collapsed && (
        <div className="px-4 pt-6 pb-2 flex-shrink-0">
          <div className="flex items-center gap-1.5">
            <Clock size={10} style={{ color: "rgba(255,255,255,0.3)" }} />
            <span className="text-xs" style={{ color: "rgba(255,255,255,0.3)", letterSpacing: "0.07em" }}>
              RECENT
            </span>
          </div>
        </div>
      )}

      {/* Search */}
      {!collapsed && (
        <div className="px-4 pb-4 flex-shrink-0">
          <div className="relative">
            <Search size={12} className="absolute left-4 top-1/2 -translate-y-1/2" style={{ color: "rgba(255,255,255,0.3)" }} />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search chats…"
              className="w-full pl-8 pr-4 py-2 rounded-lg text-xs outline-none"
              style={{
                background: "rgba(255,255,255,0.07)",
                color: "var(--sidebar-foreground)",
                border: "1px solid rgba(255,255,255,0.08)",
                caretColor: "var(--sidebar-primary)",
                fontFamily: "var(--font-sans)",
              }}
            />
          </div>
        </div>
      )}

      {/* History */}
      {!collapsed && (
        <div className="flex-1 overflow-y-auto px-4 pb-6" style={{ scrollbarWidth: "none" }}>
          {/* Close any open menu when clicking outside */}
          {menuOpenId && (
            <div className="fixed inset-0 z-10" onClick={() => setMenuOpenId(null)} />
          )}
          {groups.map((group) => {
            const groupChats = filtered.filter((c) => c.group === group);
            if (groupChats.length === 0) return null;
            return (
              <div key={group} className="mb-4">
                <button
                  onClick={() => toggleGroup(group)}
                  className="flex items-center gap-2 px-2 py-1 text-xs w-full mb-2"
                  style={{ color: "rgba(255,255,255,0.35)" }}
                >
                  {expandedGroups[group] ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                  {group === "Pinned" ? "📌 Pinned" : group}
                </button>
                {expandedGroups[group] &&
                  groupChats.map((chat) => {
                    const isActive = activeChatId === chat.id && activeView === "chat";
                    const isRenaming = renamingId === chat.id;
                    return (
                      <div
                        key={chat.id}
                        className="relative flex items-start rounded-lg mb-0.5 group/chat"
                        style={{
                          background: isActive ? "rgba(255,255,255,0.1)" : "transparent",
                        }}
                      >
                        {/* Main clickable area */}
                        <button
                          onClick={() => { if (!isRenaming) { onChatSelect(chat.id); onViewChange("chat"); } }}
                          className="flex items-start gap-2 px-4 py-2 text-left flex-1 min-w-0"
                          style={{ color: isActive ? "var(--sidebar-foreground)" : "rgba(255,255,255,0.55)" }}
                        >
                          <MessageSquare size={13} className="flex-shrink-0 mt-0.5" />
                          <div className="flex-1 min-w-0">
                            {isRenaming ? (
                              <input
                                ref={renameInputRef}
                                value={renameValue}
                                onChange={(e) => setRenameValue(e.target.value)}
                                onBlur={() => commitRename(chat.id)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") commitRename(chat.id);
                                  if (e.key === "Escape") setRenamingId(null);
                                }}
                                className="w-full text-xs rounded px-1 py-0.5 outline-none"
                                style={{
                                  background: "rgba(255,255,255,0.12)",
                                  color: "var(--sidebar-foreground)",
                                  border: "1px solid rgba(255,255,255,0.25)",
                                }}
                                onClick={(e) => e.stopPropagation()}
                              />
                            ) : (
                              <div className="truncate text-xs leading-snug">{chat.title}</div>
                            )}
                            <div className="text-xs opacity-40 mt-1">{chat.timestamp}</div>
                          </div>
                        </button>

                        {/* More button */}
                        {!isRenaming && (
                          <div className="relative flex-shrink-0 self-center pr-2">
                            <button
                              onClick={(e) => { e.stopPropagation(); setMenuOpenId(menuOpenId === chat.id ? null : chat.id); }}
                              className="p-1 rounded opacity-0 group-hover/chat:opacity-100 transition-opacity"
                              style={{ color: "rgba(255,255,255,0.5)" }}
                              title="More options"
                            >
                              <MoreHorizontal size={13} />
                            </button>

                            {menuOpenId === chat.id && (
                              <div
                                className="absolute right-0 top-7 z-20 w-40 rounded-xl border py-1 shadow-xl"
                                style={{
                                  background: "var(--card)",
                                  borderColor: "var(--border)",
                                }}
                              >
                                <button
                                  onClick={() => handlePin(chat.id)}
                                  className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-muted transition-colors"
                                  style={{ color: "var(--foreground)" }}
                                >
                                  <Pin size={12} />
                                  {chat.pinned ? "Unpin" : "Pin"}
                                </button>
                                <button
                                  onClick={() => handleRename(chat.id)}
                                  className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-muted transition-colors"
                                  style={{ color: "var(--foreground)" }}
                                >
                                  <Pencil size={12} />
                                  Rename
                                </button>
                                <div className="my-1 border-t border-border" />
                                <button
                                  onClick={() => handleDelete(chat.id)}
                                  className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-muted transition-colors"
                                  style={{ color: "var(--destructive)" }}
                                >
                                  <Trash2 size={12} />
                                  Delete
                                </button>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
              </div>
            );
          })}
        </div>
      )}

      {/* Collapsed: no chat history shown */}
      {collapsed && <div className="flex-1" />}

    </aside>
  );
}
