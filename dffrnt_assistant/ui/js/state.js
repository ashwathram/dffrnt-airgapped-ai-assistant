// Shared, mutable app state. Imported (by reference) wherever needed.

export const state = {
  view: 'chat',      // 'chat' | 'library'
  messages: [],      // {role:'user'|'assistant'|'notice', content, thinking?, sources?, ts}
  busy: false,       // a query is in flight
  collapsed: false,  // sidebar collapsed
  // Show the model's reasoning in a block (on) vs just a "Thinking…" label (off).
  showThinking: localStorage.getItem('showThinking') === '1',
  // Tag taxonomy (loaded from /api/tags). tagTypes: {id,name,color,description?}
  // tags: {id,name,typeId}.
  tagTypes: [],
  tags: [],
  // Chat retrieval scope: tag names the next query is restricted to (empty = all).
  chatScope: [],
  // Documents (with their tags) — used for the "N docs in scope" count.
  documents: [],
  // Saved conversations: id of the open one + light list for the sidebar.
  conversationId: null,
  conversations: [],
};

export const SUGGESTIONS = [
  { icon: 'trendingUp', text: 'Summarize our Q3 financial performance' },
  { icon: 'users', text: 'What are the main customer feedback themes?' },
  { icon: 'scale', text: 'Key points from our legal documents' },
  { icon: 'fileText', text: "What's on the 2026 roadmap?" },
];
