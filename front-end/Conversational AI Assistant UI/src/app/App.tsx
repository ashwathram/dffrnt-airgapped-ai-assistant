import { useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatView } from "./components/ChatView";
import { DocumentLibrary } from "./components/DocumentLibrary";
import {
  DEFAULT_DOCUMENTS, DEFAULT_TAGS, DEFAULT_TAG_TYPES,
  Document, Tag, TagType,
} from "./types";

type View = "chat" | "library";

export default function App() {
  const [activeView, setActiveView] = useState<View>("chat");
  const [activeChatId, setActiveChatId] = useState<string | null>("1");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const [documents, setDocuments] = useState<Document[]>(DEFAULT_DOCUMENTS);
  const [tags, setTags] = useState<Tag[]>(DEFAULT_TAGS);
  const [tagTypes, setTagTypes] = useState<TagType[]>(DEFAULT_TAG_TYPES);

  const handleNewChat = () => {
    setActiveChatId(null);
    setActiveView("chat");
  };

  const topBarTitle =
    activeView === "library"
      ? "Document Library"
      : activeChatId
      ? "Q3 Financial Report Analysis"
      : "New conversation";

  return (
    <div
      className="flex h-screen w-screen overflow-hidden"
      style={{ fontFamily: "var(--font-sans)", background: "var(--background)" }}
    >
      <Sidebar
        activeView={activeView}
        onViewChange={setActiveView}
        activeChatId={activeChatId}
        onChatSelect={setActiveChatId}
        onNewChat={handleNewChat}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
      />

      <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* Top bar */}
        <div
          className="flex items-center justify-between px-6 h-14 flex-shrink-0"
          style={{
            background: "var(--card)",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">{topBarTitle}</span>
          </div>
          <div />
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0">
          {activeView === "library" ? (
            <DocumentLibrary
              documents={documents}
              tags={tags}
              tagTypes={tagTypes}
              onDocumentsChange={setDocuments}
              onTagsChange={setTags}
              onTagTypesChange={setTagTypes}
            />
          ) : (
            <ChatView
              key={activeChatId ?? "new"}
              chatId={activeChatId}
              tags={tags}
              tagTypes={tagTypes}
              documents={documents}
            />
          )}
        </div>
      </main>
    </div>
  );
}
